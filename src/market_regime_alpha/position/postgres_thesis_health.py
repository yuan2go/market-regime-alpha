"""Native PostgreSQL authority for immutable, Builder-replayable H5 observations."""

from __future__ import annotations

import json
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, ThesisId
from market_regime_alpha.evidence.canonical import require_sha256
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisHealthObservationV2,
    ThesisHealthRuleConfiguration,
    ThesisInvalidationRuleSet,
    VerifiedThesisHealthBundle,
    thesis_health_command_hash,
)


class PostgresThesisHealthRepository(NativePostgresRepository):
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)

    def save_observation(
        self,
        observation: ThesisHealthObservationV2,
        *,
        input_bundle: ThesisHealthInputBundle,
        idempotency_key: str,
        command_hash: str,
    ) -> ThesisHealthObservationV2:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        if command_hash != thesis_health_command_hash(input_bundle):
            raise ValueError("Thesis health command hash does not match input bundle")
        with self._connect() as connection:
            try:
                acquire_scope_lock(
                    connection,
                    namespace="thesis-health",
                    identity=str(observation.thesis_id),
                )
                replay = _resolve_command(
                    connection,
                    idempotency_key=idempotency_key,
                    command_hash=command_hash,
                )
                if replay is not None:
                    connection.commit()
                    return replay
                _validate_latest_prior(connection, observation)
                existing = connection.execute(
                    """
                    SELECT * FROM thesis_health_observations
                    WHERE observation_id = %s OR content_hash = %s
                    """,
                    (str(observation.observation_id), observation.content_hash),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO thesis_health_observations(
                            observation_id, thesis_id, thesis_version,
                            observed_health_state, effective_health_state,
                            content_hash, input_bundle_id, input_bundle_hash,
                            configuration_id, configuration_hash,
                            rule_set_id, rule_set_hash, prior_observation_id,
                            prior_observation_hash, observation_json,
                            input_bundle_json, configuration_json,
                            rule_set_json, prior_observation_json, assessed_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        _row_values(observation, input_bundle),
                    )
                else:
                    stored, stored_bundle = _restore_row(
                        connection,
                        existing,
                        ancestry=frozenset({observation.observation_id}),
                    )
                    if stored != observation or stored_bundle != input_bundle:
                        raise ValueError("Thesis health Observation identity conflict")
                connection.execute(
                    """
                    INSERT INTO thesis_health_commands(
                        idempotency_key, command_hash, observation_id, created_at
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(observation.observation_id),
                        observation.assessed_at,
                    ),
                )
                stored = _load_observation(connection, observation.observation_id)
                connection.commit()
                return stored
            except Exception:
                connection.rollback()
                raise

    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> ThesisHealthObservationV2 | None:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            return _resolve_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )

    def get_observation(
        self, observation_id: ArtifactId
    ) -> ThesisHealthObservationV2:
        with self._connect() as connection:
            return _load_observation(connection, observation_id)

    def get_latest_observation(
        self, thesis_id: ThesisId
    ) -> ThesisHealthObservationV2 | None:
        with self._connect() as connection:
            row = _chain_tip(connection, thesis_id)
            if row is None:
                return None
            return _load_observation(
                connection, ArtifactId(str(row["observation_id"]))
            )

    def get_verified_thesis_health_bundle(
        self, observation_id: ArtifactId
    ) -> VerifiedThesisHealthBundle:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM thesis_health_observations WHERE observation_id = %s",
                (str(observation_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown ThesisHealthObservation: {observation_id}")
            observation, bundle = _restore_row(
                connection,
                row,
                ancestry=frozenset({observation_id}),
            )
            tip = _chain_tip(connection, observation.thesis_id)
            return VerifiedThesisHealthBundle(
                observation=observation,
                input_bundle=bundle,
                is_latest=(
                    tip is not None
                    and str(tip["observation_id"])
                    == str(observation.observation_id)
                ),
            )


def _resolve_command(
    connection: PostgresConnection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> ThesisHealthObservationV2 | None:
    row = connection.execute(
        """
        SELECT command_hash, observation_id, created_at
        FROM thesis_health_commands WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command_hash:
        raise ValueError("idempotency key reused for different Thesis health command")
    observation_row = connection.execute(
        "SELECT * FROM thesis_health_observations WHERE observation_id = %s",
        (str(row["observation_id"]),),
    ).fetchone()
    if observation_row is None:
        raise ValueError("Thesis health command references a missing Observation")
    observation, bundle = _restore_row(
        connection,
        observation_row,
        ancestry=frozenset({ArtifactId(str(row["observation_id"]))}),
    )
    if (
        thesis_health_command_hash(bundle) != row["command_hash"]
        or aware_datetime(row["created_at"], label="created_at")
        != observation.assessed_at
    ):
        raise ValueError("Thesis health command projection mismatch")
    return observation


def _load_observation(
    connection: PostgresConnection,
    observation_id: ArtifactId,
    *,
    ancestry: frozenset[ArtifactId] = frozenset(),
) -> ThesisHealthObservationV2:
    if observation_id in ancestry:
        raise ValueError("Thesis health prior Observation cycle detected")
    row = connection.execute(
        "SELECT * FROM thesis_health_observations WHERE observation_id = %s",
        (str(observation_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown ThesisHealthObservationV2: {observation_id}")
    return _restore_row(
        connection,
        row,
        ancestry=ancestry | {observation_id},
    )[0]


def _restore_row(
    connection: PostgresConnection,
    row: dict[str, Any],
    *,
    ancestry: frozenset[ArtifactId],
) -> tuple[ThesisHealthObservationV2, ThesisHealthInputBundle]:
    observation = ThesisHealthObservationV2.from_canonical_dict(
        _object_json(str(row["observation_json"]))
    )
    bundle = ThesisHealthInputBundle.from_canonical_dict(
        _object_json(str(row["input_bundle_json"]))
    )
    configuration = ThesisHealthRuleConfiguration.from_canonical_dict(
        _object_json(str(row["configuration_json"]))
    )
    rule_set = ThesisInvalidationRuleSet.from_canonical_dict(
        _object_json(str(row["rule_set_json"]))
    )
    prior_payload = row["prior_observation_json"]
    prior = (
        ThesisHealthObservationV2.from_canonical_dict(
            _object_json(str(prior_payload))
        )
        if prior_payload is not None
        else None
    )
    projection = (
        row["observation_id"] == str(observation.observation_id)
        and row["thesis_id"] == str(observation.thesis_id)
        and int(row["thesis_version"]) == observation.thesis_version
        and row["observed_health_state"] == observation.observed_health_state.value
        and row["effective_health_state"]
        == (
            observation.effective_health_state.value
            if observation.effective_health_state is not None
            else None
        )
        and row["content_hash"] == observation.content_hash
        and row["input_bundle_id"] == str(bundle.input_bundle_id)
        and row["input_bundle_hash"] == bundle.content_hash
        and row["configuration_id"] == str(configuration.configuration_id)
        and row["configuration_hash"] == configuration.configuration_hash
        and row["rule_set_id"] == str(rule_set.rule_set_id)
        and row["rule_set_hash"] == rule_set.rule_set_hash
        and row["prior_observation_id"]
        == (str(prior.observation_id) if prior is not None else None)
        and row["prior_observation_hash"]
        == (prior.content_hash if prior is not None else None)
        and aware_datetime(row["assessed_at"], label="assessed_at")
        == observation.assessed_at
    )
    if not projection:
        raise ValueError("Thesis health Observation projection is invalid")
    if (
        bundle.configuration != configuration
        or bundle.rule_set != rule_set
        or bundle.prior_observation != prior
        or observation.configuration_id != configuration.configuration_id
        or observation.configuration_hash != configuration.configuration_hash
        or observation.rule_set_id != rule_set.rule_set_id
        or observation.rule_set_hash != rule_set.rule_set_hash
        or observation.prior_observation_id
        != (prior.observation_id if prior is not None else None)
        or observation.prior_observation_hash
        != (prior.content_hash if prior is not None else None)
    ):
        raise ValueError("Thesis health replay references are invalid")
    if prior is not None:
        stored_prior = _load_observation(
            connection,
            prior.observation_id,
            ancestry=ancestry,
        )
        if stored_prior != prior:
            raise ValueError("Thesis health prior Observation reference is invalid")
    expected = ThesisHealthObservationBuilder().build(bundle)
    if expected != observation:
        raise ValueError("Thesis health Observation Builder replay mismatch")
    return observation, bundle


def _validate_latest_prior(
    connection: PostgresConnection,
    observation: ThesisHealthObservationV2,
) -> None:
    latest = _chain_tip(connection, observation.thesis_id)
    expected = (
        str(observation.prior_observation_id)
        if observation.prior_observation_id is not None
        else None
    )
    if latest is None:
        if expected is not None:
            raise ValueError("prior Observation is not stored")
        return
    if expected != latest["observation_id"]:
        raise ValueError("Thesis health command does not bind latest prior Observation")
    if observation.prior_observation_hash != latest["content_hash"]:
        raise ValueError("latest prior Observation hash mismatch")


def _chain_tip(
    connection: PostgresConnection,
    thesis_id: ThesisId,
) -> dict[str, Any] | None:
    rows = connection.execute(
        """
        SELECT parent.observation_id, parent.content_hash
        FROM thesis_health_observations AS parent
        WHERE parent.thesis_id = %s
          AND NOT EXISTS (
              SELECT 1
              FROM thesis_health_observations AS child
              WHERE child.prior_observation_id = parent.observation_id
          )
        """,
        (str(thesis_id),),
    ).fetchall()
    if len(rows) > 1:
        raise ValueError("Thesis health Observation chain has multiple tips")
    return rows[0] if rows else None


def _row_values(
    observation: ThesisHealthObservationV2,
    bundle: ThesisHealthInputBundle,
) -> tuple[object, ...]:
    prior = bundle.prior_observation
    return (
        str(observation.observation_id),
        str(observation.thesis_id),
        observation.thesis_version,
        observation.observed_health_state.value,
        (
            observation.effective_health_state.value
            if observation.effective_health_state is not None
            else None
        ),
        observation.content_hash,
        str(bundle.input_bundle_id),
        bundle.content_hash,
        str(bundle.configuration.configuration_id),
        bundle.configuration.configuration_hash,
        str(bundle.rule_set.rule_set_id),
        bundle.rule_set.rule_set_hash,
        str(prior.observation_id) if prior is not None else None,
        prior.content_hash if prior is not None else None,
        _json(observation.to_canonical_dict()),
        _json(bundle.to_canonical_dict()),
        _json(bundle.configuration.to_canonical_dict()),
        _json(bundle.rule_set.to_canonical_dict()),
        _json(prior.to_canonical_dict()) if prior is not None else None,
        observation.assessed_at,
    )


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
        raise ValueError("Thesis health Repository JSON must be an object")
    return payload


__all__ = ["PostgresThesisHealthRepository"]
