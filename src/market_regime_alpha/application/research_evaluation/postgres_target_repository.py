"""PostgreSQL authority for target protocols and target-scoped outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Callable

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    TargetedShadowOutcome,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


Clock = Callable[[], datetime]


class TargetOutcomeConflict(ValueError):
    """Target protocol or settlement idempotency/lineage conflict."""


class TargetOutcomeIntegrityError(ValueError):
    """Stored target protocol or settlement failed canonical restoration."""


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class PostgresTargetOutcomeRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _now,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        self._clock = clock
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def register_protocol(self, protocol: OutcomeTargetProtocol) -> OutcomeTargetProtocol:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO outcome_target_protocol(
                    protocol_id, protocol_hash, protocol_version, protocol_json, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (protocol_id) DO NOTHING
                """,
                (
                    str(protocol.protocol_id),
                    protocol.protocol_hash,
                    protocol.protocol_version,
                    Jsonb(protocol.to_canonical_dict()),
                    self._clock(),
                ),
            )
            stored = connection.execute(
                "SELECT protocol_hash FROM outcome_target_protocol WHERE protocol_id = %s",
                (str(protocol.protocol_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != protocol.protocol_hash:
                raise TargetOutcomeConflict("Target Protocol identity conflict")
            for target in protocol.targets:
                connection.execute(
                    """
                    INSERT INTO outcome_target_definition(
                        protocol_id, target_id, target_hash, target_version,
                        checkpoint, target_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (protocol_id, target_id) DO NOTHING
                    """,
                    (
                        str(protocol.protocol_id),
                        str(target.target_id),
                        target.target_hash,
                        target.target_version,
                        target.checkpoint.value,
                        Jsonb(target.to_canonical_dict()),
                    ),
                )

        self._factory.run_transaction(operation)
        return self.get_protocol(protocol.protocol_id)

    def get_protocol(self, protocol_id: ArtifactId) -> OutcomeTargetProtocol:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT protocol_json, protocol_hash FROM outcome_target_protocol WHERE protocol_id = %s",
                (str(protocol_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(protocol_id))
        try:
            protocol = OutcomeTargetProtocol.from_canonical_dict(_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TargetOutcomeIntegrityError("Target Protocol restoration failed") from exc
        if protocol.protocol_hash != str(row[1]):
            raise TargetOutcomeIntegrityError("Target Protocol owner hash drift")
        return protocol

    def settle(self, outcome: TargetedShadowOutcome) -> TargetedShadowOutcome:
        self.register_protocol(self.get_protocol(outcome.target_protocol_id))

        def operation(connection: Any) -> None:
            decision = connection.execute(
                "SELECT decision_hash FROM shadow_research_decision WHERE decision_id = %s",
                (str(outcome.shadow_decision.artifact_id),),
            ).fetchone()
            factual = connection.execute(
                "SELECT settlement_hash, shadow_decision_id, "
                "source_dataset_id, source_dataset_hash "
                "FROM prospective_outcome_settlement WHERE settlement_id = %s",
                (str(outcome.factual_outcome_v1.artifact_id),),
            ).fetchone()
            protocol = connection.execute(
                "SELECT protocol_hash FROM outcome_target_protocol WHERE protocol_id = %s",
                (str(outcome.target_protocol_id),),
            ).fetchone()
            if decision is None or str(decision[0]) != outcome.shadow_decision.content_hash:
                raise TargetOutcomeConflict("Targeted Outcome Decision lineage mismatch")
            if factual is None or (
                str(factual[0]) != outcome.factual_outcome_v1.content_hash
                or str(factual[1]) != str(outcome.shadow_decision.artifact_id)
                or str(factual[2]) != str(outcome.source_dataset.artifact_id)
                or str(factual[3]) != outcome.source_dataset.content_hash
            ):
                raise TargetOutcomeConflict("Targeted Outcome V1 lineage mismatch")
            if protocol is None or str(protocol[0]) != outcome.target_protocol_hash:
                raise TargetOutcomeConflict("Targeted Outcome Protocol lineage mismatch")
            connection.execute(
                """
                INSERT INTO targeted_shadow_outcome(
                    settlement_id, settlement_hash, shadow_decision_id,
                    factual_outcome_v1_id, target_protocol_id, source_dataset_id,
                    next_session_date, availability_status, outcome_available_at,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (settlement_id) DO NOTHING
                """,
                (
                    str(outcome.settlement_id),
                    outcome.settlement_hash,
                    str(outcome.shadow_decision.artifact_id),
                    str(outcome.factual_outcome_v1.artifact_id),
                    str(outcome.target_protocol_id),
                    str(outcome.source_dataset.artifact_id),
                    outcome.next_session_date,
                    outcome.availability_status.value,
                    outcome.outcome_available_at,
                    Jsonb(outcome.to_canonical_dict()),
                    outcome.created_at,
                ),
            )
            stored = connection.execute(
                "SELECT settlement_hash FROM targeted_shadow_outcome WHERE settlement_id = %s",
                (str(outcome.settlement_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != outcome.settlement_hash:
                raise TargetOutcomeConflict("Targeted Outcome identity conflict")
            for label in outcome.labels:
                connection.execute(
                    """
                    INSERT INTO targeted_shadow_outcome_label(
                        settlement_id, label_id, label_hash, target_protocol_id,
                        target_id, symbol, label_interval_start, label_interval_end,
                        availability_status, label_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (settlement_id, label_id) DO NOTHING
                    """,
                    (
                        str(outcome.settlement_id),
                        str(label.label_id),
                        label.label_hash,
                        str(outcome.target_protocol_id),
                        str(label.target.artifact_id),
                        label.symbol,
                        label.label_interval_start,
                        label.label_interval_end,
                        label.availability_status.value,
                        Jsonb(label.to_canonical_dict()),
                    ),
                )

        self._factory.run_transaction(operation)
        return self.get(outcome.settlement_id)

    def get(self, settlement_id: ArtifactId) -> TargetedShadowOutcome:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, settlement_hash FROM targeted_shadow_outcome WHERE settlement_id = %s",
                (str(settlement_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(settlement_id))
        try:
            outcome = TargetedShadowOutcome.from_canonical_dict(_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise TargetOutcomeIntegrityError("Targeted Outcome restoration failed") from exc
        if outcome.settlement_hash != str(row[1]):
            raise TargetOutcomeIntegrityError("Targeted Outcome owner hash drift")
        return outcome

    def replay(self, settlement_id: ArtifactId) -> TargetedShadowOutcome:
        stored = self.get(settlement_id)
        rebuilt = TargetedShadowOutcome.create(**{name: getattr(stored, name) for name in _outcome_value_names()})
        if rebuilt != stored:
            raise TargetOutcomeIntegrityError("Targeted Outcome replay mismatch")
        return rebuilt


def _outcome_value_names() -> tuple[str, ...]:
    return (
        "shadow_decision",
        "factual_outcome_v1",
        "source_dataset",
        "target_protocol_id",
        "target_protocol_hash",
        "next_session_date",
        "labels",
        "availability_status",
        "outcome_available_at",
        "created_at",
        "reason_codes",
        "limitations",
    )


def _object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TargetOutcomeIntegrityError("stored target payload is not an object")
    return value


__all__ = [
    "PostgresTargetOutcomeRepository",
    "TargetOutcomeConflict",
    "TargetOutcomeIntegrityError",
]
