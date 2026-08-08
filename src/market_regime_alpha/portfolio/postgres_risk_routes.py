"""PostgreSQL-native authority for immutable H4 reducing-risk decision bundles."""

from __future__ import annotations

import json
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
    RiskReducingDecision,
    RiskReducingExecutionGate,
    RiskReducingGateConfiguration,
    VerifiedRiskReducingDecisionBundle,
)
from market_regime_alpha.position.authority import PositionSnapshot
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)

class PostgresRiskRouteRepository(NativePostgresRepository):
    """Native PostgreSQL RiskRouteRepository."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)

    def save_reducing_decision(
        self,
        decision: RiskReducingDecision,
        *,
        position: PositionSnapshot,
        execution_observation: ReducingExecutionObservation,
        configuration: RiskReducingGateConfiguration,
        idempotency_key: str,
        command_hash: str,
    ) -> RiskReducingDecision:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            acquire_scope_lock(
                connection,
                namespace="risk-reducing-position",
                identity=position.position_book_id,
            )
            try:
                replay = _resolve_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if replay is not None:
                    connection.commit()
                    return replay
                existing = connection.execute(
                    """
                    SELECT * FROM risk_reducing_decisions
                    WHERE decision_id = %s OR content_hash = %s
                    """,
                    (str(decision.decision_id), decision.content_hash),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO risk_reducing_decisions(
                            decision_id, position_snapshot_id, position_book_id,
                            thesis_id, action, state, content_hash, position_json,
                            observation_json, configuration_json, decision_json,
                            assessed_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(decision.decision_id),
                            str(decision.position_snapshot_id),
                            str(decision.position_book_id),
                            str(decision.thesis_id),
                            decision.action.value,
                            decision.state.value,
                            decision.content_hash,
                            _json(position.to_canonical_dict()),
                            _json(execution_observation.to_canonical_dict()),
                            _json(configuration.to_canonical_dict()),
                            _json(decision.to_canonical_dict()),
                            decision.assessed_at,
                        ),
                    )
                else:
                    stored = _restore_bundle(existing)
                    if stored != (
                        position,
                        execution_observation,
                        configuration,
                        decision,
                    ):
                        raise ValueError("risk-reducing decision identity conflict")
                connection.execute(
                    """
                    INSERT INTO risk_reducing_commands(
                        idempotency_key, command_hash, decision_id, created_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(decision.decision_id),
                        decision.assessed_at,
                    ),
                )
                stored_decision = _load_reducing_decision(
                    connection, decision.decision_id
                )
                connection.commit()
                return stored_decision
            except Exception:
                connection.rollback()
                raise

    def resolve_reducing_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> RiskReducingDecision | None:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            return _resolve_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )

    def get_reducing_decision(
        self, decision_id: ArtifactId
    ) -> RiskReducingDecision:
        with self._connect() as connection:
            return _load_reducing_decision(connection, decision_id)

    def get_verified_reducing_decision_bundle(
        self, decision_id: ArtifactId
    ) -> VerifiedRiskReducingDecisionBundle:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM risk_reducing_decisions WHERE decision_id = %s",
                (str(decision_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown RiskReducingDecision: {decision_id}")
            position, observation, configuration, decision = _restore_bundle(row)
            return VerifiedRiskReducingDecisionBundle(
                position=position,
                execution_observation=observation,
                configuration=configuration,
                decision=decision,
            )


def _resolve_command(
    connection: PostgresConnection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> RiskReducingDecision | None:
    row = connection.execute(
        """
        SELECT command_hash, decision_id FROM risk_reducing_commands
        WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command_hash:
        raise ValueError("idempotency key reused for different risk-route command")
    return _load_reducing_decision(
        connection, ArtifactId(str(row["decision_id"]))
    )


def _load_reducing_decision(
    connection: PostgresConnection, decision_id: ArtifactId
) -> RiskReducingDecision:
    row = connection.execute(
        "SELECT * FROM risk_reducing_decisions WHERE decision_id = %s",
        (str(decision_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown RiskReducingDecision: {decision_id}")
    return _restore_bundle(row)[3]


def _restore_bundle(
    row: dict[str, Any],
) -> tuple[
    PositionSnapshot,
    ReducingExecutionObservation,
    RiskReducingGateConfiguration,
    RiskReducingDecision,
]:
    position = PositionSnapshot.from_canonical_dict(
        _object_json(str(row["position_json"]))
    )
    observation = ReducingExecutionObservation.from_canonical_dict(
        _object_json(str(row["observation_json"]))
    )
    configuration = RiskReducingGateConfiguration.from_canonical_dict(
        _object_json(str(row["configuration_json"]))
    )
    decision = RiskReducingDecision.from_canonical_dict(
        _object_json(str(row["decision_json"]))
    )
    position_hash = canonical_hash(position.to_canonical_dict())
    if (
        row["decision_id"] != str(decision.decision_id)
        or row["position_snapshot_id"] != str(decision.position_snapshot_id)
        or row["position_book_id"] != str(decision.position_book_id)
        or row["thesis_id"] != str(decision.thesis_id)
        or row["action"] != decision.action.value
        or row["state"] != decision.state.value
        or row["content_hash"] != decision.content_hash
        or aware_datetime(row["assessed_at"], label="assessed_at")
        != decision.assessed_at
    ):
        raise ValueError("risk-reducing decision projection is invalid")
    if (
        decision.position_snapshot_id != position.snapshot_id
        or decision.position_snapshot_hash != position_hash
        or decision.position_snapshot_version != position.version
        or decision.position_book_id != position.position_book_id
        or decision.thesis_id != position.thesis_id
        or decision.symbol != position.symbol
        or decision.current_quantity != position.total_quantity
        or decision.available_quantity != (position.available_quantity or 0)
        or decision.observation_id != observation.observation_id
        or decision.observation_hash != observation.content_hash
        or decision.configuration_id != configuration.configuration_id
        or decision.configuration_hash != configuration.configuration_hash
    ):
        raise ValueError("risk-reducing decision evidence references are invalid")
    expected = RiskReducingExecutionGate().assess(
        action=decision.action,
        position=position,
        target_quantity=decision.target_quantity,
        order_quantity=decision.order_quantity,
        execution_observation=observation,
        configuration=configuration,
        actor=decision.actor,
        reason=decision.reason,
        assessed_at=decision.assessed_at,
    )
    if expected != decision:
        raise ValueError("risk-reducing decision is not reconstructible")
    return position, observation, configuration, decision


def _key(value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("idempotency key must be a non-empty trimmed string")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("risk-route repository JSON must be an object")
    return payload


__all__ = ["PostgresRiskRouteRepository"]
