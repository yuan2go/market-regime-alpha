"""PostgreSQL CAS journal and immutable Artifact store for Strategy Shadow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.strategy_shadow.contracts import (
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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


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
                "SELECT payload_json FROM strategy_shadow_session WHERE session_id = %s", (str(session_id),)
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
        return strategy_shadow_session_from_canonical_dict(payload)

    def list_sessions(self, *, trading_date: date) -> tuple[StrategyShadowSession, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT session_id FROM strategy_shadow_session WHERE trading_date = %s ORDER BY session_id",
                (trading_date,),
            ).fetchall()
        return tuple(self.get(ArtifactId(str(row[0]))) for row in rows)

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
                    policy_id, status, revision, payload_json, created_at,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
