"""PostgreSQL owner for Research Universe Policy and Runtime Scope receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.universe.operational import OperationalUniverseArtifact
from market_regime_alpha.universe.runtime_scope import (
    ResearchUniversePolicy,
    RuntimeScopeDecision,
    RuntimeScopeReceipt,
)


class PostgresRuntimeScopeRepository:
    """Own immutable policies/receipts and validate every projection on reload."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def register_policy(self, policy: ResearchUniversePolicy) -> ResearchUniversePolicy:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO research_universe_policy(
                    policy_id, policy_hash, policy_version, data_authority,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (policy_id) DO NOTHING
                """,
                (
                    str(policy.policy_id),
                    policy.policy_hash,
                    policy.policy_version,
                    policy.data_authority,
                    Jsonb(policy.to_canonical_dict()),
                ),
            )
            row = connection.execute(
                "SELECT policy_hash FROM research_universe_policy WHERE policy_id = %s",
                (str(policy.policy_id),),
            ).fetchone()
            if row is None or str(row[0]) != policy.policy_hash:
                raise ValueError("Research Universe Policy identity conflict")

        self._factory.run_transaction(operation)
        return self.get_policy(policy.policy_id)

    def publish(
        self,
        *,
        policy: ResearchUniversePolicy,
        receipt: RuntimeScopeReceipt,
        operational_universes: tuple[OperationalUniverseArtifact, ...] = (),
    ) -> RuntimeScopeReceipt:
        if receipt.policy_id != policy.policy_id or receipt.policy_hash != policy.policy_hash:
            raise ValueError("Runtime Scope receipt does not bind the supplied Policy")

        def operation(connection: Any) -> None:
            self._insert_policy(connection, policy)
            included = sum(
                item.decision is RuntimeScopeDecision.INCLUDED
                for item in receipt.records
            )
            unknown = sum(
                item.decision is RuntimeScopeDecision.UNKNOWN
                for item in receipt.records
            )
            connection.execute(
                """
                INSERT INTO runtime_scope_receipt(
                    scope_id, scope_hash, policy_id, policy_hash, as_of,
                    built_at, code_revision, data_eligibility, evidence_ceiling,
                    formal_pit, member_count, included_count, unknown_count,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                ) ON CONFLICT (scope_id) DO NOTHING
                """,
                (
                    str(receipt.scope_id),
                    receipt.scope_hash,
                    str(receipt.policy_id),
                    receipt.policy_hash,
                    receipt.as_of,
                    receipt.built_at,
                    receipt.code_revision,
                    receipt.data_eligibility,
                    receipt.evidence_ceiling,
                    receipt.formal_pit,
                    len(receipt.records),
                    included,
                    unknown,
                    Jsonb(receipt.to_canonical_dict()),
                    receipt.built_at,
                ),
            )
            row = connection.execute(
                "SELECT scope_hash FROM runtime_scope_receipt WHERE scope_id = %s",
                (str(receipt.scope_id),),
            ).fetchone()
            if row is None or str(row[0]) != receipt.scope_hash:
                raise ValueError("Runtime Scope receipt identity conflict")
            for ordinal, reference in enumerate(receipt.input_references, start=1):
                connection.execute(
                    """
                    INSERT INTO runtime_scope_input_reference(
                        scope_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (scope_id, ordinal) DO NOTHING
                    """,
                    (
                        str(receipt.scope_id),
                        ordinal,
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
                    ),
                )
            for item in receipt.records:
                connection.execute(
                    """
                    INSERT INTO runtime_scope_member(
                        scope_id, symbol, decision, payload_json
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (scope_id, symbol) DO NOTHING
                    """,
                    (
                        str(receipt.scope_id),
                        item.symbol,
                        item.decision.value,
                        Jsonb(item.to_canonical_dict()),
                    ),
                )
            expected_inputs = {
                (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                )
                for item in receipt.input_references
            }
            for ordinal, universe in enumerate(
                sorted(operational_universes, key=lambda item: str(item.universe_id)),
                start=1,
            ):
                universe.verify_identity()
                if (
                    "OPERATIONAL_UNIVERSE",
                    str(universe.universe_id),
                    universe.content_hash,
                ) not in expected_inputs:
                    raise ValueError(
                        "Runtime Scope Operational Universe is not input-bound"
                    )
                connection.execute(
                    """
                    INSERT INTO runtime_scope_operational_input(
                        scope_id, ordinal, universe_id, universe_hash,
                        decision_date, effective_at, available_at,
                        payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scope_id, ordinal) DO NOTHING
                    """,
                    (
                        str(receipt.scope_id),
                        ordinal,
                        str(universe.universe_id),
                        universe.content_hash,
                        universe.decision_date,
                        universe.effective_at,
                        universe.available_at,
                        Jsonb(universe.to_canonical_dict()),
                        receipt.built_at,
                    ),
                )
            self._verify_counts(connection, receipt)
            if operational_universes:
                self._verify_operational_inputs(
                    connection,
                    receipt,
                    operational_universes,
                )

        self._factory.run_transaction(operation)
        return self.get(receipt.scope_id)

    def get_policy(self, policy_id: ArtifactId) -> ResearchUniversePolicy:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT policy_hash, payload_json FROM research_universe_policy "
                "WHERE policy_id = %s",
                (str(policy_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(policy_id))
        policy = ResearchUniversePolicy.from_canonical_dict(row[1])
        if str(row[0]) != policy.policy_hash:
            raise ValueError("Research Universe Policy owner hash diverged")
        return policy

    def get(self, scope_id: ArtifactId) -> RuntimeScopeReceipt:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT scope_hash, payload_json FROM runtime_scope_receipt "
                "WHERE scope_id = %s",
                (str(scope_id),),
            ).fetchone()
            references = connection.execute(
                """
                SELECT artifact_kind, artifact_id, content_hash
                FROM runtime_scope_input_reference
                WHERE scope_id = %s ORDER BY ordinal
                """,
                (str(scope_id),),
            ).fetchall()
            members = connection.execute(
                "SELECT decision, payload_json FROM runtime_scope_member "
                "WHERE scope_id = %s ORDER BY symbol",
                (str(scope_id),),
            ).fetchall()
        if row is None or not isinstance(row[1], dict):
            raise KeyError(str(scope_id))
        receipt = RuntimeScopeReceipt.from_canonical_dict(row[1])
        if str(row[0]) != receipt.scope_hash:
            raise ValueError("Runtime Scope owner hash diverged")
        expected_references = tuple(
            (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            )
            for item in receipt.input_references
        )
        if tuple(tuple(str(value) for value in item) for item in references) != (
            expected_references
        ):
            raise ValueError("Runtime Scope input projection diverged")
        expected_members = tuple(
            (item.decision.value, item.to_canonical_dict()) for item in receipt.records
        )
        if tuple((str(item[0]), item[1]) for item in members) != expected_members:
            raise ValueError("Runtime Scope member projection diverged")
        return receipt

    def resolve(
        self,
        *,
        policy_id: ArtifactId,
        as_of: datetime,
        known_at: datetime,
    ) -> RuntimeScopeReceipt:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT scope_id
                FROM runtime_scope_receipt
                WHERE policy_id = %s AND as_of = %s AND built_at <= %s
                ORDER BY built_at DESC, scope_id DESC
                LIMIT 1
                """,
                (str(policy_id), as_of, known_at),
            ).fetchone()
        if row is None:
            raise KeyError("no Runtime Scope receipt was known at that time")
        return self.get(ArtifactId(str(row[0])))

    def get_operational_inputs(
        self, scope_id: ArtifactId
    ) -> tuple[OperationalUniverseArtifact, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT universe_id, universe_hash, payload_json
                FROM runtime_scope_operational_input
                WHERE scope_id = %s ORDER BY ordinal
                """,
                (str(scope_id),),
            ).fetchall()
        if not rows:
            raise KeyError("Runtime Scope Operational Universe inputs are missing")
        result: list[OperationalUniverseArtifact] = []
        for row in rows:
            if not isinstance(row[2], dict):
                raise ValueError("Runtime Scope Operational Universe payload is invalid")
            universe = OperationalUniverseArtifact.from_canonical_dict(row[2])
            if (str(row[0]), str(row[1])) != (
                str(universe.universe_id),
                universe.content_hash,
            ):
                raise ValueError("Operational Universe projection diverged")
            result.append(universe)
        return tuple(result)

    @staticmethod
    def _insert_policy(connection: Any, policy: ResearchUniversePolicy) -> None:
        connection.execute(
            """
            INSERT INTO research_universe_policy(
                policy_id, policy_hash, policy_version, data_authority,
                payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (policy_id) DO NOTHING
            """,
            (
                str(policy.policy_id),
                policy.policy_hash,
                policy.policy_version,
                policy.data_authority,
                Jsonb(policy.to_canonical_dict()),
            ),
        )
        row = connection.execute(
            "SELECT policy_hash FROM research_universe_policy WHERE policy_id = %s",
            (str(policy.policy_id),),
        ).fetchone()
        if row is None or str(row[0]) != policy.policy_hash:
            raise ValueError("Research Universe Policy identity conflict")

    @staticmethod
    def _verify_counts(connection: Any, receipt: RuntimeScopeReceipt) -> None:
        reference_count = connection.execute(
            "SELECT count(*) FROM runtime_scope_input_reference WHERE scope_id = %s",
            (str(receipt.scope_id),),
        ).fetchone()
        member_count = connection.execute(
            "SELECT count(*) FROM runtime_scope_member WHERE scope_id = %s",
            (str(receipt.scope_id),),
        ).fetchone()
        if reference_count is None or int(reference_count[0]) != len(
            receipt.input_references
        ):
            raise ValueError("Runtime Scope input reference set is incomplete")
        if member_count is None or int(member_count[0]) != len(receipt.records):
            raise ValueError("Runtime Scope member set is incomplete")

    @staticmethod
    def _verify_operational_inputs(
        connection: Any,
        receipt: RuntimeScopeReceipt,
        operational_universes: tuple[OperationalUniverseArtifact, ...],
    ) -> None:
        rows = connection.execute(
            """
            SELECT universe_id, universe_hash, payload_json
            FROM runtime_scope_operational_input
            WHERE scope_id = %s ORDER BY ordinal
            """,
            (str(receipt.scope_id),),
        ).fetchall()
        expected = tuple(
            (
                str(item.universe_id),
                item.content_hash,
                item.to_canonical_dict(),
            )
            for item in sorted(
                operational_universes,
                key=lambda item: str(item.universe_id),
            )
        )
        actual = tuple((str(row[0]), str(row[1]), row[2]) for row in rows)
        if actual != expected:
            raise ValueError("Operational Universe projection diverged")


__all__ = ["PostgresRuntimeScopeRepository"]
