"""PostgreSQL CAS journal and immutable Artifact store for Strategy Shadow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

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
    project_strategy_position_states,
)
from market_regime_alpha.application.decision_system.contracts import (
    ManualAccountObservation,
)
from market_regime_alpha.application.strategy_shadow.postgres_observations import (
    PostgresShadowObservationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    StrategyPositionState,
)
from market_regime_alpha.strategies.sleeves import FillAllocationBatch


class PostgresStrategyShadowRepository:
    def __init__(self, factory: PostgresConnectionFactory, *, apply_migrations: bool = True) -> None:
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
    ) -> tuple[StrategyPositionState, ...]:
        """Resolve state from Fill allocations and manual account marks.

        Callers select only the account and Decision Time; quantities, prices,
        counters and lineage are all reloaded from their PostgreSQL owners.
        """

        with self._factory.connection(read_only=True) as connection:
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
            raise ValueError("Strategy Fill lineage references a missing Proposal")
        observations = tuple(
            ManualAccountObservation.from_canonical_dict(_dict_payload(row[0]))
            for row in observation_rows
        )
        return project_strategy_position_states(
            account_id=account_id,
            decision_time=decision_time,
            batches=batches,
            proposal_actions=actions,
            observations=observations,
        )

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


def _dict_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("PostgreSQL owner payload must be an object")
    return value
