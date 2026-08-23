"""PostgreSQL CAS journal and immutable Artifact store for Strategy Shadow."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, cast

from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    ShadowEntry,
    StrategyShadowPolicy,
    restore_strategy_shadow_artifact,
    strategy_shadow_artifact_payload,
)
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowArtifactKind,
    StrategyShadowArtifactRecord,
    StrategyShadowSession,
    strategy_shadow_session_from_canonical_dict,
)
from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ObservationKind,
    ShadowObservationReceipt,
)
from market_regime_alpha.application.strategy_shadow.multi_strategy_lifecycle import (
    FillDerivedStrategyOutcome,
    project_strategy_position_states,
    settle_fill_derived_strategy_outcomes,
)
from market_regime_alpha.application.strategy_shadow.postgres_observations import (
    PostgresShadowObservationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.execution.manual import Fill, FillKind
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    MultiStrategyCycle,
    StrategyPositionState,
)
from market_regime_alpha.strategies.sleeves import (
    FillAllocationBatch,
    effective_fill_allocation_batches,
)


class PostgresStrategyShadowRepository:
    def __init__(self, factory: PostgresConnectionFactory, *, apply_migrations: bool = False) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def save_policy(
        self, policy: StrategyShadowPolicy, *, created_at: datetime
    ) -> StrategyShadowPolicy:
        payload = strategy_shadow_artifact_payload(policy)

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO strategy_shadow_policy_authority(
                    policy_id, policy_hash, policy_json,
                    real_order_authority, real_fill_authority,
                    real_position_authority, created_at
                ) VALUES (%s, %s, %s, false, false, false, %s)
                ON CONFLICT (policy_id) DO NOTHING
                """,
                (
                    str(policy.policy_id),
                    policy.policy_hash,
                    Jsonb(payload),
                    created_at,
                ),
            )
            stored = connection.execute(
                """
                SELECT policy_hash, policy_json, real_order_authority,
                       real_fill_authority, real_position_authority
                FROM strategy_shadow_policy_authority WHERE policy_id = %s
                """,
                (str(policy.policy_id),),
            ).fetchone()
            if stored is None or (
                str(stored[0]) != policy.policy_hash
                or stored[1] != payload
                or bool(stored[2])
                or bool(stored[3])
                or bool(stored[4])
            ):
                raise ValueError("Strategy Shadow Policy immutable identity conflict")

        self._factory.run_transaction(operation)
        return self.get_policy(policy.policy_id)

    def get_policy(self, policy_id: ArtifactId) -> StrategyShadowPolicy:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT policy_hash, policy_json
                FROM strategy_shadow_policy_authority WHERE policy_id = %s
                """,
                (str(policy_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(policy_id))
        restored = restore_strategy_shadow_artifact(
            artifact_kind="POLICY",
            artifact_id=policy_id,
            artifact_hash=str(row[0]),
            payload=row[1],
        )
        if not isinstance(restored, StrategyShadowPolicy):
            raise ValueError("Strategy Shadow Policy owner restored invalid type")
        return restored

    def save(self, session: StrategyShadowSession, *, expected_revision: int | None) -> StrategyShadowSession:
        self._factory.run_transaction(
            lambda connection: self._save_session(connection, session=session, expected_revision=expected_revision)
        )
        return self.get(session.session_id)

    def save_with_artifact(
        self,
        session: StrategyShadowSession,
        *,
        expected_revision: int,
        artifact: StrategyShadowArtifactRecord,
    ) -> StrategyShadowSession:
        if artifact.session_id != session.session_id:
            raise ValueError("Strategy Shadow Artifact/session mismatch")

        def operation(connection: Any) -> None:
            self._save_session(connection, session=session, expected_revision=expected_revision)
            self._insert_artifact(connection, artifact)

        self._factory.run_transaction(operation)
        return self.get(session.session_id)

    def save_artifact(self, artifact: StrategyShadowArtifactRecord) -> None:
        self._factory.run_transaction(lambda connection: self._insert_artifact(connection, artifact))

    def get(self, session_id: ArtifactId) -> StrategyShadowSession:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, lineage_status FROM strategy_shadow_session "
                "WHERE session_id = %s",
                (str(session_id),),
            ).fetchone()
            event_rows = connection.execute(
                """
                SELECT payload_json
                FROM strategy_shadow_event
                WHERE session_id = %s
                ORDER BY sequence
                """,
                (str(session_id),),
            ).fetchall()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(session_id))
        event_payloads = [item[0] for item in event_rows]
        if any(not isinstance(item, dict) for item in event_payloads):
            raise ValueError("Strategy Shadow durable event payload is invalid")
        payload = {**row[0], "events": event_payloads}
        session = strategy_shadow_session_from_canonical_dict(payload)
        if str(row[1]) == "EXACT_V1":
            with self._factory.connection(read_only=True) as connection:
                self._verify_session_lineage(connection, session)
        return session

    def list_sessions(self, *, trading_date: date) -> tuple[StrategyShadowSession, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT session_id FROM strategy_shadow_session WHERE trading_date = %s ORDER BY session_id",
                (trading_date,),
            ).fetchall()
        return tuple(self.get(ArtifactId(str(row[0]))) for row in rows)

    def resolve_multi_strategy_positions(
        self,
        *,
        account_id: str,
        decision_time: datetime,
        trading_calendar_reference: RuntimeArtifactReference,
    ) -> tuple[StrategyPositionState, ...]:
        """Resolve state from Fill allocations and manual account marks.

        Callers select only the account and Decision Time; quantities, prices,
        counters and lineage are all reloaded from their PostgreSQL owners.
        """

        if trading_calendar_reference.reference_kind != "TRADING_CALENDAR":
            raise ValueError("Strategy state requires a Trading Calendar reference")
        trading_calendar = PostgresPITTradingCalendarSnapshotRepository(
            self._factory,
            apply_migrations=False,
        ).get(trading_calendar_reference.artifact_id)
        if trading_calendar.content_hash != trading_calendar_reference.content_hash:
            raise ValueError("Strategy Trading Calendar owner identity mismatch")

        def operation(connection: Any) -> tuple[StrategyPositionState, ...]:
            acquire_scope_lock(
                connection,
                namespace="strategy-execution-account",
                identity=account_id,
            )
            batch_rows = connection.execute(
                """
                SELECT payload_json
                FROM strategy_fill_allocation_batch
                WHERE account_id = %s AND created_at <= %s
                ORDER BY created_at, batch_id
                """,
                (account_id, decision_time),
            ).fetchall()
            observation_rows = connection.execute(
                """
                SELECT payload_json
                FROM manual_account_observation
                WHERE account_id = %s AND as_of_time <= %s
                ORDER BY trading_date, revision
                """,
                (account_id, decision_time),
            ).fetchall()
            batches = tuple(
                FillAllocationBatch.from_canonical_dict(_dict_payload(row[0]))
                for row in batch_rows
            )
            _require_effective_fill_allocation_heads(
                connection,
                account_id=account_id,
                decision_time=decision_time,
                batches=batches,
            )
            proposal_references = {
                allocation.proposal_reference.artifact_id: allocation.proposal_reference
                for batch in batches
                for allocation in batch.allocations
            }
            proposal_rows = (
                ()
                if not proposal_references
                else connection.execute(
                    """
                    SELECT proposal_id, proposal_hash, action
                    FROM strategy_proposal
                    WHERE proposal_id = ANY(%s)
                    """,
                    ([str(item) for item in proposal_references],),
                ).fetchall()
            )
            actions: dict[ArtifactId, CanonicalStrategyAction] = {}
            for row in proposal_rows:
                proposal_id = ArtifactId(str(row[0]))
                expected = proposal_references.get(proposal_id)
                if expected is None or str(row[1]) != expected.content_hash:
                    raise ValueError("Strategy Proposal owner identity mismatch")
                actions[proposal_id] = CanonicalStrategyAction(str(row[2]))
            if set(actions) != set(proposal_references):
                raise ValueError(
                    "Strategy Fill lineage references a missing Proposal"
                )
            observations = tuple(
                ManualAccountObservation.from_canonical_dict(
                    _dict_payload(row[0])
                )
                for row in observation_rows
            )
            return project_strategy_position_states(
                account_id=account_id,
                decision_time=decision_time,
                batches=batches,
                proposal_actions=actions,
                observations=observations,
                trading_calendar=trading_calendar,
            )

        return self._factory.run_transaction(operation)

    def settle_multi_strategy_outcomes(
        self,
        *,
        account_id: str,
        decision_time: datetime,
    ) -> tuple[FillDerivedStrategyOutcome, ...]:
        """Recover and persist every completed allocated-Fill lifecycle."""

        def operation(connection: Any) -> tuple[FillDerivedStrategyOutcome, ...]:
            acquire_scope_lock(
                connection,
                namespace="strategy-execution-account",
                identity=account_id,
            )
            batch_rows = connection.execute(
                """
                SELECT payload_json
                FROM strategy_fill_allocation_batch
                WHERE account_id = %s AND created_at <= %s
                ORDER BY created_at, batch_id
                """,
                (account_id, decision_time),
            ).fetchall()
            batches = tuple(
                FillAllocationBatch.from_canonical_dict(_dict_payload(row[0]))
                for row in batch_rows
            )
            proposal_references = {
                allocation.proposal_reference.artifact_id: allocation.proposal_reference
                for batch in batches
                for allocation in batch.allocations
            }
            proposal_rows = (
                ()
                if not proposal_references
                else connection.execute(
                    """
                    SELECT p.proposal_id, p.proposal_hash, p.action,
                           p.strategy_version_id, p.symbol, c.payload_json
                    FROM strategy_proposal AS p
                    JOIN strategy_run AS r ON r.run_id = p.run_id
                    JOIN multi_strategy_cycle AS c ON c.cycle_id = r.cycle_id
                    WHERE p.proposal_id = ANY(%s)
                    """,
                    ([str(item) for item in proposal_references],),
                ).fetchall()
            )
            actions: dict[ArtifactId, CanonicalStrategyAction] = {}
            pre_exit_states: dict[ArtifactId, StrategyPositionState] = {}
            for row in proposal_rows:
                proposal_id = ArtifactId(str(row[0]))
                expected = proposal_references.get(proposal_id)
                if expected is None or str(row[1]) != expected.content_hash:
                    raise ValueError("Strategy Proposal owner identity mismatch")
                action = CanonicalStrategyAction(str(row[2]))
                actions[proposal_id] = action
                if action is not CanonicalStrategyAction.EXIT:
                    continue
                cycle = MultiStrategyCycle.from_canonical_dict(
                    _dict_payload(row[5])
                )
                matched = tuple(
                    state
                    for state in cycle.runtime_input.positions
                    if str(state.strategy_version_id) == str(row[3])
                    and state.symbol == str(row[4])
                )
                if len(matched) != 1 or matched[0].state_reference is None:
                    raise ValueError(
                        "EXIT Proposal lacks owner-resolved pre-exit state"
                    )
                pre_exit_states[proposal_id] = matched[0]
            if set(actions) != set(proposal_references):
                raise ValueError(
                    "Strategy Fill lineage references a missing Proposal"
                )
            outcomes = settle_fill_derived_strategy_outcomes(
                account_id=account_id,
                decision_time=decision_time,
                batches=batches,
                proposal_actions=actions,
                pre_exit_states=pre_exit_states,
            )
            return self._save_multi_strategy_outcomes(
                connection,
                outcomes,
            )

        return self._factory.run_transaction(operation)

    def get_multi_strategy_outcome(
        self,
        outcome_id: ArtifactId,
    ) -> FillDerivedStrategyOutcome:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_realized_outcome
                WHERE outcome_id = %s
                """,
                (str(outcome_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(outcome_id))
        return FillDerivedStrategyOutcome.from_canonical_dict(
            _dict_payload(row[0])
        )

    @staticmethod
    def _save_multi_strategy_outcomes(
        connection: Any,
        outcomes: tuple[FillDerivedStrategyOutcome, ...],
    ) -> tuple[FillDerivedStrategyOutcome, ...]:
        persisted: list[FillDerivedStrategyOutcome] = []
        for outcome in outcomes:
            scope = (
                f"{outcome.account_id}:"
                f"{outcome.strategy_version_reference.artifact_id}:"
                f"{outcome.symbol}:{outcome.entry_proposal_reference.artifact_id}"
            )
            acquire_scope_lock(
                connection,
                namespace="strategy-realized-outcome",
                identity=scope,
            )
            PostgresStrategyShadowRepository._verify_outcome_fill_heads(
                connection,
                outcome,
            )
            head_row = connection.execute(
                """
                SELECT payload_json
                FROM strategy_realized_outcome
                WHERE account_id = %s AND strategy_version_id = %s
                  AND symbol = %s AND entry_proposal_id = %s
                ORDER BY revision DESC LIMIT 1
                FOR SHARE
                """,
                (
                    outcome.account_id,
                    str(outcome.strategy_version_reference.artifact_id),
                    outcome.symbol,
                    str(outcome.entry_proposal_reference.artifact_id),
                ),
            ).fetchone()
            if head_row is not None:
                head = FillDerivedStrategyOutcome.from_canonical_dict(
                    _dict_payload(head_row[0])
                )
                if _outcome_economic_payload(head) == _outcome_economic_payload(
                    outcome
                ):
                    persisted.append(head)
                    continue
                head_source_time = _outcome_source_head_time(connection, head)
                candidate_source_time = _outcome_source_head_time(connection, outcome)
                if head_source_time > candidate_source_time:
                    # A correction-settlement won the lifecycle lock while this
                    # candidate was computed from an older Fill view. Outcome
                    # heads are monotonic; stale work cannot supersede it.
                    persisted.append(head)
                    continue
                if head_source_time == candidate_source_time:
                    raise ValueError(
                        "Strategy Outcome has conflicting economics at one Fill head"
                    )
                outcome = _superseding_outcome(outcome, head)
            PostgresStrategyShadowRepository._verify_multi_strategy_outcome_lineage(
                connection,
                outcome,
            )
            payload = outcome.to_canonical_dict()
            connection.execute(
                """
                INSERT INTO strategy_realized_outcome(
                    outcome_id, outcome_hash, account_id,
                    strategy_version_id, strategy_version_hash,
                    entry_proposal_id, entry_proposal_hash,
                    exit_proposal_id, exit_proposal_hash,
                    pre_exit_state_id, pre_exit_state_hash,
                    symbol, opened_at, closed_at, invested_notional,
                    gross_pnl, total_cost, net_pnl, net_return,
                    source_allocation_ids, source_fill_ids,
                    revision, supersedes_outcome_id, supersedes_outcome_hash,
                    production_authorized, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, false, %s, %s
                ) ON CONFLICT (outcome_id) DO NOTHING
                """,
                (
                    str(outcome.outcome_id),
                    outcome.outcome_hash,
                    outcome.account_id,
                    str(outcome.strategy_version_reference.artifact_id),
                    outcome.strategy_version_reference.content_hash,
                    str(outcome.entry_proposal_reference.artifact_id),
                    outcome.entry_proposal_reference.content_hash,
                    str(outcome.exit_proposal_reference.artifact_id),
                    outcome.exit_proposal_reference.content_hash,
                    str(outcome.pre_exit_state_reference.artifact_id),
                    outcome.pre_exit_state_reference.content_hash,
                    outcome.symbol,
                    outcome.opened_at,
                    outcome.closed_at,
                    outcome.invested_notional,
                    outcome.gross_pnl,
                    outcome.total_cost,
                    outcome.net_pnl,
                    outcome.net_return,
                    [
                        str(item.artifact_id)
                        for item in outcome.source_allocation_references
                    ],
                    [
                        str(item.artifact_id)
                        for item in outcome.source_fill_references
                    ],
                    outcome.revision,
                    (
                        str(outcome.supersedes_outcome_reference.artifact_id)
                        if outcome.supersedes_outcome_reference is not None
                        else None
                    ),
                    (
                        outcome.supersedes_outcome_reference.content_hash
                        if outcome.supersedes_outcome_reference is not None
                        else None
                    ),
                    Jsonb(payload),
                    outcome.settled_at,
                ),
            )
            stored = connection.execute(
                """
                SELECT outcome_hash, payload_json, production_authorized
                FROM strategy_realized_outcome WHERE outcome_id = %s
                """,
                (str(outcome.outcome_id),),
            ).fetchone()
            if (
                stored is None
                or str(stored[0]) != outcome.outcome_hash
                or stored[1] != payload
                or bool(stored[2])
            ):
                raise ValueError("Strategy Outcome immutable identity conflict")
            persisted.append(outcome)
        return tuple(persisted)

    @staticmethod
    def _verify_outcome_fill_heads(
        connection: Any,
        outcome: FillDerivedStrategyOutcome,
    ) -> None:
        """Reject settlement computed before a committed Fill Correction."""

        fill_ids = [
            str(item.artifact_id) for item in outcome.source_fill_references
        ]
        rows = connection.execute(
            """
            SELECT fill_id, fill_kind
            FROM manual_fills
            WHERE fill_id = ANY(%s)
            """,
            (fill_ids,),
        ).fetchall()
        if {str(item[0]) for item in rows} != set(fill_ids):
            raise ValueError("Strategy Outcome source Fill is missing")
        execution_ids = [
            str(item[0]) for item in rows if str(item[1]) == "EXECUTION"
        ]
        if execution_ids:
            corrected = connection.execute(
                """
                SELECT correction_of_fill_id
                FROM manual_fills
                WHERE correction_of_fill_id = ANY(%s)
                LIMIT 1
                """,
                (execution_ids,),
            ).fetchone()
            if corrected is not None:
                raise ValueError(
                    "RECONCILIATION_REQUIRED: Strategy Outcome source Fill "
                    "is not the current correction head"
                )

    @staticmethod
    def _verify_multi_strategy_outcome_lineage(
        connection: Any,
        outcome: FillDerivedStrategyOutcome,
    ) -> None:
        for proposal, action in (
            (outcome.entry_proposal_reference, "ENTER"),
            (outcome.exit_proposal_reference, "EXIT"),
        ):
            row = connection.execute(
                """
                SELECT action, strategy_version_id, strategy_version_hash, symbol
                FROM strategy_proposal
                WHERE proposal_id = %s AND proposal_hash = %s
                FOR SHARE
                """,
                (str(proposal.artifact_id), proposal.content_hash),
            ).fetchone()
            if row is None or (
                str(row[0]) != action
                or str(row[1])
                != str(outcome.strategy_version_reference.artifact_id)
                or str(row[2])
                != outcome.strategy_version_reference.content_hash
                or str(row[3]) != outcome.symbol
            ):
                raise ValueError("Strategy Outcome Proposal lineage mismatch")
        allocation_rows = connection.execute(
            """
            SELECT a.allocation_id, a.allocation_hash,
                   b.source_fill_id, b.source_fill_hash, b.account_id
            FROM strategy_fill_allocation AS a
            JOIN strategy_fill_allocation_batch AS b ON b.batch_id = a.batch_id
            WHERE a.allocation_id = ANY(%s)
            FOR SHARE OF a, b
            """,
            ([str(item.artifact_id) for item in outcome.source_allocation_references],),
        ).fetchall()
        actual_allocations = {
            (str(row[0]), str(row[1])) for row in allocation_rows
        }
        expected_allocations = {
            (str(item.artifact_id), item.content_hash)
            for item in outcome.source_allocation_references
        }
        actual_fills = {(str(row[2]), str(row[3])) for row in allocation_rows}
        expected_fills = {
            (str(item.artifact_id), item.content_hash)
            for item in outcome.source_fill_references
        }
        if (
            actual_allocations != expected_allocations
            or actual_fills != expected_fills
            or any(str(row[4]) != outcome.account_id for row in allocation_rows)
        ):
            raise ValueError("Strategy Outcome Fill lineage mismatch")

    def get_artifact(
        self,
        *,
        session_id: ArtifactId,
        artifact_kind: StrategyShadowArtifactKind,
    ) -> StrategyShadowArtifactRecord | None:
        rows = self.list_artifacts(
            session_id=session_id,
            artifact_kind=artifact_kind,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError(f"Strategy Shadow {artifact_kind.value} Artifact is not unique")
        return rows[0]

    def list_artifacts(
        self,
        *,
        session_id: ArtifactId,
        artifact_kind: StrategyShadowArtifactKind | None = None,
    ) -> tuple[StrategyShadowArtifactRecord, ...]:
        predicate = "" if artifact_kind is None else " AND artifact_kind = %s"
        parameters = (
            (str(session_id),)
            if artifact_kind is None
            else (str(session_id), artifact_kind.value)
        )
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_hash, artifact_kind,
                       payload_json, created_at
                FROM strategy_shadow_artifact
                WHERE session_id = %s
                """ + predicate + " ORDER BY created_at, artifact_id",
                parameters,
            ).fetchall()
        output = []
        for row in rows:
            if not isinstance(row[3], dict):
                raise ValueError("Strategy Shadow Artifact payload is invalid")
            stored_kind = StrategyShadowArtifactKind(str(row[2]))
            reference_kind = {
                StrategyShadowArtifactKind.POLICY: "STRATEGY_SHADOW_POLICY",
                StrategyShadowArtifactKind.LIQUIDITY_OBSERVATION: "FREE_DATA_SHADOW_LIQUIDITY_OBSERVATION",
                StrategyShadowArtifactKind.ENTRY: "SHADOW_ENTRY",
                StrategyShadowArtifactKind.FILL: "SHADOW_FILL",
                StrategyShadowArtifactKind.POSITION: "SHADOW_POSITION",
                StrategyShadowArtifactKind.HOLDING_ASSESSMENT: "HOLDING_ASSESSMENT",
                StrategyShadowArtifactKind.EXIT_ASSESSMENT: "EXIT_ASSESSMENT",
                StrategyShadowArtifactKind.STRATEGY_OUTCOME: "STRATEGY_OUTCOME",
                StrategyShadowArtifactKind.DAILY_REPORT: "STRATEGY_SHADOW_DAILY_REPORT",
            }[stored_kind]
            output.append(
                StrategyShadowArtifactRecord(
                    artifact_reference=ValidationArtifactReference(
                        reference_kind,
                        ArtifactId(str(row[0])),
                        str(row[1]),
                    ),
                    artifact_kind=stored_kind,
                    session_id=session_id,
                    payload=row[3],
                    created_at=row[4],
                )
            )
        return tuple(output)

    @staticmethod
    def _save_session(
        connection: Any,
        *,
        session: StrategyShadowSession,
        expected_revision: int | None,
    ) -> None:
        PostgresStrategyShadowRepository._verify_required_session_owners(
            connection,
            session,
        )
        row = connection.execute(
            "SELECT revision FROM strategy_shadow_session WHERE session_id = %s FOR UPDATE", (str(session.session_id),)
        ).fetchone()
        actual = None if row is None else int(row[0])
        if actual != expected_revision:
            raise ValueError("Strategy Shadow PostgreSQL CAS conflict")
        if row is None:
            connection.execute(
                """
                INSERT INTO strategy_shadow_session(
                    session_id, session_hash, trading_date, scheduled_for,
                    research_shadow_id, runtime_run_id, runtime_tick_id,
                    policy_id, status, revision, payload_json, lineage_status,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'EXACT_V1', %s, %s
                )
                """,
                (
                    str(session.session_id),
                    session.session_hash,
                    session.trading_date,
                    session.scheduled_for,
                    str(session.research_shadow_reference.artifact_id),
                    str(session.runtime_run_reference.artifact_id),
                    str(session.runtime_tick_reference.artifact_id),
                    str(session.policy_reference.artifact_id),
                    session.status.value,
                    session.revision,
                    Jsonb(session.to_canonical_dict()),
                    session.created_at,
                    session.updated_at,
                ),
            )
            PostgresStrategyShadowRepository._append_session_lineage(
                connection,
                session.session_id,
                (
                    session.research_shadow_reference,
                    session.runtime_run_reference,
                    session.runtime_tick_reference,
                    session.policy_reference,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE strategy_shadow_session
                SET session_hash = %s, status = %s, revision = %s,
                    payload_json = %s, updated_at = %s
                WHERE session_id = %s AND revision = %s
                """,
                (
                    session.session_hash,
                    session.status.value,
                    session.revision,
                    Jsonb(session.to_canonical_dict()),
                    session.updated_at,
                    str(session.session_id),
                    expected_revision,
                ),
            )
        for event in session.events:
            connection.execute(
                """
                INSERT INTO strategy_shadow_event(
                    session_id, sequence, event_id, event_hash, event_kind,
                    occurred_at, artifact_id, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id, sequence) DO NOTHING
                """,
                (
                    str(session.session_id),
                    event.sequence,
                    str(event.event_id),
                    event.event_hash,
                    event.event_kind.value,
                    event.occurred_at,
                    None if event.artifact_reference is None else str(event.artifact_reference.artifact_id),
                    Jsonb(event.to_canonical_dict()),
                ),
            )
            stored = connection.execute(
                "SELECT event_hash FROM strategy_shadow_event WHERE session_id = %s AND sequence = %s",
                (str(session.session_id), event.sequence),
            ).fetchone()
            if stored is None or str(stored[0]) != event.event_hash:
                raise ValueError("Strategy Shadow event identity conflict")

    @staticmethod
    def _insert_artifact(connection: Any, artifact: StrategyShadowArtifactRecord) -> None:
        connection.execute(
            """
            INSERT INTO strategy_shadow_artifact(
                artifact_id, artifact_hash, session_id, artifact_kind,
                real_trading_mutation, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, false, %s, %s)
            ON CONFLICT (artifact_id) DO NOTHING
            """,
            (
                str(artifact.artifact_reference.artifact_id),
                artifact.artifact_reference.content_hash,
                None if artifact.session_id is None else str(artifact.session_id),
                artifact.artifact_kind.value,
                Jsonb(artifact.payload),
                artifact.created_at,
            ),
        )
        stored = connection.execute(
            "SELECT artifact_hash, session_id FROM strategy_shadow_artifact WHERE artifact_id = %s",
            (str(artifact.artifact_reference.artifact_id),),
        ).fetchone()
        expected_session = None if artifact.session_id is None else str(artifact.session_id)
        if stored is None or str(stored[0]) != artifact.artifact_reference.content_hash or stored[1] != expected_session:
            raise ValueError("Strategy Shadow Artifact identity conflict")
        if (
            artifact.artifact_kind is StrategyShadowArtifactKind.ENTRY
            and PostgresStrategyShadowRepository._is_typed_entry_payload(
                artifact.payload
            )
        ):
            restored = restore_strategy_shadow_artifact(
                artifact_kind=artifact.artifact_kind.value,
                artifact_id=artifact.artifact_reference.artifact_id,
                artifact_hash=artifact.artifact_reference.content_hash,
                payload=artifact.payload,
            )
            if not isinstance(restored, ShadowEntry) or artifact.session_id is None:
                raise ValueError("Strategy Shadow Entry owner restored invalid type")
            PostgresStrategyShadowRepository._append_session_lineage(
                connection,
                artifact.session_id,
                restored.source_references,
            )

    @staticmethod
    def _append_session_lineage(
        connection: Any,
        session_id: ArtifactId,
        references: tuple[ValidationArtifactReference, ...],
    ) -> None:
        row = connection.execute(
            "SELECT coalesce(max(ordinal), 0) "
            "FROM strategy_shadow_session_lineage_binding WHERE session_id = %s",
            (str(session_id),),
        ).fetchone()
        ordinal = 0 if row is None else int(row[0])
        existing = {
            (str(item[0]), str(item[1]), str(item[2]))
            for item in connection.execute(
                "SELECT artifact_kind, artifact_id, content_hash "
                "FROM strategy_shadow_session_lineage_binding WHERE session_id = %s",
                (str(session_id),),
            ).fetchall()
        }
        for reference in sorted(
            references,
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        ):
            key = (
                reference.artifact_kind,
                str(reference.artifact_id),
                reference.content_hash,
            )
            if key in existing:
                continue
            ordinal += 1
            connection.execute(
                """
                INSERT INTO strategy_shadow_session_lineage_binding(
                    session_id, ordinal, artifact_kind, artifact_id, content_hash
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (str(session_id), ordinal, *key),
            )
            existing.add(key)

    @staticmethod
    def _verify_session_lineage(
        connection: Any,
        session: StrategyShadowSession,
    ) -> None:
        PostgresStrategyShadowRepository._verify_required_session_owners(
            connection,
            session,
        )
        rows = connection.execute(
            "SELECT artifact_kind, artifact_id, content_hash "
            "FROM strategy_shadow_session_lineage_binding "
            "WHERE session_id = %s ORDER BY ordinal",
            (str(session.session_id),),
        ).fetchall()
        actual = {
            ValidationArtifactReference(
                str(row[0]), ArtifactId(str(row[1])), str(row[2])
            )
            for row in rows
        }
        required = {
            session.research_shadow_reference,
            session.runtime_run_reference,
            session.runtime_tick_reference,
            session.policy_reference,
        }
        entry_row = connection.execute(
            "SELECT artifact_id, artifact_hash, payload_json "
            "FROM strategy_shadow_artifact "
            "WHERE session_id = %s AND artifact_kind = 'ENTRY'",
            (str(session.session_id),),
        ).fetchone()
        if entry_row is not None and isinstance(entry_row[2], dict) and (
            PostgresStrategyShadowRepository._is_typed_entry_payload(entry_row[2])
        ):
            restored = restore_strategy_shadow_artifact(
                artifact_kind="ENTRY",
                artifact_id=ArtifactId(str(entry_row[0])),
                artifact_hash=str(entry_row[1]),
                payload=entry_row[2],
            )
            if not isinstance(restored, ShadowEntry):
                raise ValueError("Strategy Shadow Entry owner restored invalid type")
            required.update(restored.source_references)
        if actual != required:
            raise ValueError("Strategy Shadow durable lineage projection diverged")
        for reference in actual:
            if reference.artifact_kind != "SHADOW_OBSERVATION_RECEIPT":
                continue
            owner = connection.execute(
                "SELECT receipt_hash, observed_at, payload_json "
                "FROM shadow_observation_receipt "
                "WHERE receipt_id = %s",
                (str(reference.artifact_id),),
            ).fetchone()
            if (
                owner is None
                or str(owner[0]) != reference.content_hash
                or session.updated_at < owner[1]
                or not isinstance(owner[2], dict)
            ):
                raise ValueError("Strategy Shadow Observation receipt owner mismatch")
            receipt = ShadowObservationReceipt.from_canonical_dict(owner[2])
            if (
                receipt.kind is not ObservationKind.STRATEGY
                or receipt.receipt_id != reference.artifact_id
                or receipt.receipt_hash != reference.content_hash
                or receipt.research_trading_date != session.trading_date
            ):
                raise ValueError("Strategy Shadow Observation receipt lineage mismatch")
            PostgresShadowObservationRepository._verify_projections(
                connection,
                receipt,
            )
            PostgresShadowObservationRepository._verify_typed_owner_chain(
                connection,
                receipt,
            )

    @staticmethod
    def _verify_required_session_owners(
        connection: Any,
        session: StrategyShadowSession,
    ) -> None:
        decision = connection.execute(
            """
            SELECT decision.decision_hash, decision.run_id, decision.tick_id,
                   decision.decision_frozen_at, shadow.trading_date
            FROM shadow_research_decision AS decision
            JOIN shadow_research_session AS shadow
              ON shadow.session_id = decision.session_id
            WHERE decision.decision_id = %s
            """,
            (str(session.research_shadow_reference.artifact_id),),
        ).fetchone()
        run = connection.execute(
            """
            SELECT command_hash, trading_date, created_at
            FROM continuous_research_run WHERE run_id = %s
            """,
            (str(session.runtime_run_reference.artifact_id),),
        ).fetchone()
        tick = connection.execute(
            """
            SELECT tick_hash, run_id, observed_at, created_at
            FROM continuous_runtime_tick WHERE tick_id = %s
            """,
            (str(session.runtime_tick_reference.artifact_id),),
        ).fetchone()
        policy = connection.execute(
            """
            SELECT policy_hash, created_at
            FROM strategy_shadow_policy_authority WHERE policy_id = %s
            """,
            (str(session.policy_reference.artifact_id),),
        ).fetchone()
        if decision is None or (
            str(decision[0]) != session.research_shadow_reference.content_hash
            or str(decision[1]) != str(session.runtime_run_reference.artifact_id)
            or str(decision[2]) != str(session.runtime_tick_reference.artifact_id)
            or decision[3] > session.created_at
            or decision[4] != session.trading_date
        ):
            raise ValueError("Strategy Shadow Decision owner identity/time mismatch")
        if run is None or (
            str(run[0]) != session.runtime_run_reference.content_hash
            or run[1] != session.trading_date
            or run[2] > session.created_at
        ):
            raise ValueError("Strategy Shadow Runtime Run owner identity/time mismatch")
        if tick is None or (
            str(tick[0]) != session.runtime_tick_reference.content_hash
            or str(tick[1]) != str(session.runtime_run_reference.artifact_id)
            or max(tick[2], tick[3]) > session.created_at
        ):
            raise ValueError("Strategy Shadow Runtime Tick owner identity/time mismatch")
        if policy is None or (
            str(policy[0]) != session.policy_reference.content_hash
            or policy[1] > session.created_at
        ):
            raise ValueError("Strategy Shadow Policy owner identity/time mismatch")

    @staticmethod
    def _is_typed_entry_payload(payload: dict[str, Any]) -> bool:
        """Distinguish the canonical Entry owner from legacy generic artifacts.

        The pre-067 repository contract admitted opaque engineering payloads for
        every artifact kind.  Those rows remain readable and hash-checked, but
        only the canonical Entry shape contributes durable owner lineage.
        """

        typed_markers = {
            "assessment_reference",
            "policy_reference",
            "source_references",
        }
        present = typed_markers.intersection(payload)
        if present and present != typed_markers:
            raise ValueError("Strategy Shadow Entry typed lineage payload is incomplete")
        return present == typed_markers


def _require_effective_fill_allocation_heads(
    connection: Any,
    *,
    account_id: str,
    decision_time: datetime,
    batches: tuple[FillAllocationBatch, ...],
) -> None:
    rows = connection.execute(
        """
        SELECT f.fill_json
        FROM manual_fills AS f
        JOIN manual_trade_records AS t
          ON t.manual_trade_id = f.manual_trade_id
        WHERE f.account_id = %s
          AND f.recorded_at <= %s
          AND t.authority_route = 'STRATEGY'
        ORDER BY f.recorded_at, f.fill_id
        """,
        (account_id, decision_time),
    ).fetchall()
    fills = tuple(
        Fill.from_canonical_dict(
            _dict_payload(
                item[0]
                if isinstance(item[0], dict)
                else json.loads(str(item[0]))
            )
        )
        for item in rows
    )
    executions = {
        item.fill_id: item for item in fills if item.fill_kind is FillKind.EXECUTION
    }
    corrections = {
        item.correction_of_fill_id: item
        for item in fills
        if item.fill_kind is FillKind.CORRECTION
    }
    effective_fill_ids = {
        str(corrections.get(fill_id, original).fill_id)
        for fill_id, original in executions.items()
    }
    effective_allocation_ids = {
        str(item.source_fill_id)
        for item in effective_fill_allocation_batches(batches)
    }
    if effective_fill_ids != effective_allocation_ids:
        raise ValueError(
            "RECONCILIATION_REQUIRED: effective Strategy Fill allocation "
            "is incomplete at Decision Time"
        )


def _outcome_economic_payload(
    outcome: FillDerivedStrategyOutcome,
) -> dict[str, object]:
    payload = outcome.identity_payload()
    for field in (
        "schema_version",
        "settled_at",
        "revision",
        "supersedes_outcome_reference",
    ):
        payload.pop(field, None)
    return payload


def _outcome_source_head_time(
    connection: Any,
    outcome: FillDerivedStrategyOutcome,
) -> datetime:
    fill_ids = [str(item.artifact_id) for item in outcome.source_fill_references]
    row = connection.execute(
        """
        SELECT max(recorded_at), count(*)
        FROM manual_fills
        WHERE fill_id = ANY(%s)
        """,
        (fill_ids,),
    ).fetchone()
    if row is None or row[0] is None or int(row[1]) != len(fill_ids):
        raise ValueError("Strategy Outcome Fill head is not reloadable")
    return cast(datetime, row[0])


def _superseding_outcome(
    candidate: FillDerivedStrategyOutcome,
    previous: FillDerivedStrategyOutcome,
) -> FillDerivedStrategyOutcome:
    return FillDerivedStrategyOutcome.create(
        account_id=candidate.account_id,
        strategy_version_reference=candidate.strategy_version_reference,
        entry_proposal_reference=candidate.entry_proposal_reference,
        exit_proposal_reference=candidate.exit_proposal_reference,
        pre_exit_state_reference=candidate.pre_exit_state_reference,
        symbol=candidate.symbol,
        opened_at=candidate.opened_at,
        closed_at=candidate.closed_at,
        invested_notional=candidate.invested_notional,
        gross_pnl=candidate.gross_pnl,
        total_cost=candidate.total_cost,
        net_pnl=candidate.net_pnl,
        net_return=candidate.net_return,
        source_allocation_references=candidate.source_allocation_references,
        source_fill_references=candidate.source_fill_references,
        settled_at=candidate.settled_at,
        limitations=candidate.limitations,
        revision=previous.revision + 1,
        supersedes_outcome_reference=RuntimeArtifactReference(
            "STRATEGY_REALIZED_OUTCOME",
            previous.outcome_id,
            previous.outcome_hash,
        ),
    )


def _dict_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("PostgreSQL owner payload must be an object")
    return value
