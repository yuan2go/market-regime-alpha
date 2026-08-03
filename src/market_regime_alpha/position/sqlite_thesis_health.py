"""SQLite authority for immutable, Builder-replayable H5 observations."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import require_sha256
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisHealthObservationV2,
    ThesisHealthRuleConfiguration,
    ThesisInvalidationRuleSet,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
THESIS_HEALTH_UP_MIGRATION = _MIGRATION_ROOT / "008_thesis_health_up.sql"
THESIS_HEALTH_DOWN_MIGRATION = _MIGRATION_ROOT / "008_thesis_health_down.sql"

_REQUIRED_COLUMNS = {
    "thesis_health_observations": (
        "observation_id",
        "thesis_id",
        "thesis_version",
        "observed_health_state",
        "effective_health_state",
        "content_hash",
        "input_bundle_id",
        "input_bundle_hash",
        "configuration_id",
        "configuration_hash",
        "rule_set_id",
        "rule_set_hash",
        "prior_observation_id",
        "prior_observation_hash",
        "observation_json",
        "input_bundle_json",
        "configuration_json",
        "rule_set_json",
        "prior_observation_json",
        "assessed_at",
    ),
    "thesis_health_commands": (
        "idempotency_key",
        "command_hash",
        "observation_id",
        "created_at",
    ),
}

_TRIGGERS = {
    "thesis_health_observations_no_update": """
        CREATE TRIGGER thesis_health_observations_no_update
        BEFORE UPDATE ON thesis_health_observations
        BEGIN
            SELECT RAISE(ABORT, 'thesis health observations are append-only');
        END
    """,
    "thesis_health_observations_no_delete": """
        CREATE TRIGGER thesis_health_observations_no_delete
        BEFORE DELETE ON thesis_health_observations
        BEGIN
            SELECT RAISE(ABORT, 'thesis health observations are append-only');
        END
    """,
    "thesis_health_commands_no_update": """
        CREATE TRIGGER thesis_health_commands_no_update
        BEFORE UPDATE ON thesis_health_commands
        BEGIN
            SELECT RAISE(ABORT, 'thesis health commands are append-only');
        END
    """,
    "thesis_health_commands_no_delete": """
        CREATE TRIGGER thesis_health_commands_no_delete
        BEFORE DELETE ON thesis_health_commands
        BEGIN
            SELECT RAISE(ABORT, 'thesis health commands are append-only');
        END
    """,
}


class SQLiteThesisHealthRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                THESIS_HEALTH_UP_MIGRATION.read_text(encoding="utf-8")
            )
            _validate_schema(connection)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
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
                    WHERE observation_id = ? OR content_hash = ?
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        _row_values(observation, input_bundle),
                    )
                else:
                    stored, stored_bundle = _restore_row(connection, existing)
                    if stored != observation or stored_bundle != input_bundle:
                        raise ValueError("Thesis health Observation identity conflict")
                connection.execute(
                    """
                    INSERT INTO thesis_health_commands(
                        idempotency_key, command_hash, observation_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(observation.observation_id),
                        observation.assessed_at.isoformat(),
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


def _resolve_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> ThesisHealthObservationV2 | None:
    row = connection.execute(
        "SELECT command_hash, observation_id FROM thesis_health_commands WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command_hash:
        raise ValueError("idempotency key reused for different Thesis health command")
    return _load_observation(connection, ArtifactId(str(row["observation_id"])))


def _load_observation(
    connection: sqlite3.Connection,
    observation_id: ArtifactId,
) -> ThesisHealthObservationV2:
    row = connection.execute(
        "SELECT * FROM thesis_health_observations WHERE observation_id = ?",
        (str(observation_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown ThesisHealthObservationV2: {observation_id}")
    return _restore_row(connection, row)[0]


def _restore_row(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
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
        and row["assessed_at"] == observation.assessed_at.isoformat()
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
        stored_prior = connection.execute(
            "SELECT content_hash FROM thesis_health_observations WHERE observation_id = ?",
            (str(prior.observation_id),),
        ).fetchone()
        if stored_prior is None or stored_prior["content_hash"] != prior.content_hash:
            raise ValueError("Thesis health prior Observation reference is invalid")
    expected = ThesisHealthObservationBuilder().build(bundle)
    if expected != observation:
        raise ValueError("Thesis health Observation Builder replay mismatch")
    return observation, bundle


def _validate_latest_prior(
    connection: sqlite3.Connection,
    observation: ThesisHealthObservationV2,
) -> None:
    latest = connection.execute(
        """
        SELECT observation_id, content_hash FROM thesis_health_observations
        WHERE thesis_id = ? ORDER BY assessed_at DESC, observation_id DESC LIMIT 1
        """,
        (str(observation.thesis_id),),
    ).fetchone()
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
        observation.assessed_at.isoformat(),
    )


def _validate_schema(connection: sqlite3.Connection) -> None:
    migration = connection.execute(
        "SELECT 1 FROM pdl_schema_migrations WHERE version = 8"
    ).fetchone()
    if migration is None:
        raise ValueError("Thesis health migration 008 is not applied")
    for table, required_columns in _REQUIRED_COLUMNS.items():
        actual_columns = tuple(
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        if actual_columns != required_columns:
            raise ValueError(f"Thesis health table schema mismatch: {table}")
    table_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'thesis_health_observations'"
    ).fetchone()
    compact = _compact_sql(str(table_sql["sql"])) if table_sql is not None else ""
    for check in (
        "check(thesis_version>=0)",
        "check(observed_health_statein('healthy','weakening','invalidated','data_insufficient'))",
        "unique(thesis_id,assessed_at)",
    ):
        if check not in compact:
            raise ValueError("Thesis health check constraint mismatch")
    triggers = {
        str(row["name"]): str(row["sql"])
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    for name, expected_sql in _TRIGGERS.items():
        actual_sql = triggers.get(name)
        if actual_sql is None:
            raise ValueError("Thesis health append-only triggers are missing")
        if _compact_sql(actual_sql) != _compact_sql(expected_sql):
            raise ValueError(f"Thesis health append-only trigger mismatch: {name}")


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


def _compact_sql(value: str) -> str:
    return "".join(value.lower().split())
