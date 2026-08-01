"""SQLite durable adapters for Model Registry and Experiment Governance."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from market_regime_alpha.core.identity import ExperimentId, ModelId
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentAccessRecord,
    ExperimentGovernance,
    FrozenExperimentProtocol,
)
from market_regime_alpha.platform.governance_serialization import (
    experiment_protocol_from_dict,
    model_registration_from_dict,
    model_registration_to_dict,
    model_transition_from_dict,
)
from market_regime_alpha.platform.model_registry import (
    ModelRegistration,
    ModelRegistry,
)
from market_regime_alpha.platform.repositories import (
    VersionConflictError,
    VersionedExperimentGovernance,
    VersionedModelRegistration,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
GOVERNANCE_UP_MIGRATION = _MIGRATION_ROOT / "001_governance_up.sql"
GOVERNANCE_DOWN_MIGRATION = _MIGRATION_ROOT / "001_governance_down.sql"


class _SQLiteGovernanceBase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(GOVERNANCE_UP_MIGRATION.read_text())

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


class SQLiteModelRegistryRepository(_SQLiteGovernanceBase):
    """Validated model state plus append-only transition history."""

    def resolve_command(
        self,
        model_id: ModelId,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> VersionedModelRegistration | None:
        _key(idempotency_key)
        with self._connect() as connection:
            row = _command(connection, idempotency_key)
            if row is None:
                return None
            _validate_command(
                row,
                aggregate_type="MODEL",
                aggregate_id=str(model_id),
                payload_hash=command_hash,
            )
            return self._load_at(
                connection, model_id, int(row["result_version"])
            )

    def get(self, model_id: ModelId) -> VersionedModelRegistration:
        with self._connect() as connection:
            row = _model_row(connection, model_id)
            return self._load_at(connection, model_id, int(row["version"]))

    def create(
        self,
        registration: ModelRegistration,
        *,
        idempotency_key: str,
    ) -> VersionedModelRegistration:
        _key(idempotency_key)
        ModelRegistry().restore(registration)
        if registration.transitions:
            raise ValueError("new model registration cannot contain transitions")
        payload = model_registration_to_dict(registration)
        command_hash = _payload_hash(payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(
                        command,
                        aggregate_type="MODEL",
                        aggregate_id=str(registration.definition.model_id),
                        payload_hash=command_hash,
                    )
                    result = self._load_at(
                        connection,
                        registration.definition.model_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                existing = connection.execute(
                    "SELECT * FROM model_registrations WHERE model_id = ?",
                    (str(registration.definition.model_id),),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO model_registrations(
                            model_id, registration_json, definition_hash,
                            lifecycle_status, evidence_level, version
                        ) VALUES (?, ?, ?, ?, ?, 0)
                        """,
                        (
                            str(registration.definition.model_id),
                            _json(payload),
                            registration.definition.definition_hash,
                            registration.lifecycle_status.value,
                            registration.evidence_level.value,
                        ),
                    )
                    version = 0
                else:
                    current = self._load_at(
                        connection,
                        registration.definition.model_id,
                        int(existing["version"]),
                    )
                    if current.registration.definition != registration.definition:
                        raise ValueError(
                            "model identity conflict in durable registry"
                        )
                    version = current.version
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    aggregate_type="MODEL",
                    aggregate_id=str(registration.definition.model_id),
                    payload_hash=command_hash,
                    result_version=version,
                )
                result = self._load_at(
                    connection, registration.definition.model_id, version
                )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def compare_and_set(
        self,
        model_id: ModelId,
        *,
        expected_version: int,
        registration: ModelRegistration,
        idempotency_key: str,
        command_hash: str | None = None,
    ) -> VersionedModelRegistration:
        _key(idempotency_key)
        ModelRegistry().restore(registration)
        payload = model_registration_to_dict(registration)
        effective_hash = command_hash or _payload_hash(payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(
                        command,
                        aggregate_type="MODEL",
                        aggregate_id=str(model_id),
                        payload_hash=effective_hash,
                    )
                    result = self._load_at(
                        connection, model_id, int(command["result_version"])
                    )
                    connection.commit()
                    return result
                current_row = _model_row(connection, model_id)
                current_version = int(current_row["version"])
                if current_version != expected_version:
                    raise VersionConflictError(
                        f"model {model_id} expected version {expected_version}, "
                        f"found {current_version}"
                    )
                current = self._load_at(
                    connection, model_id, current_version
                ).registration
                if registration.definition != current.definition:
                    raise ValueError("model definition is immutable")
                if (
                    registration.transitions[:-1] != current.transitions
                    or len(registration.transitions)
                    != len(current.transitions) + 1
                ):
                    raise ValueError(
                        "model update must append exactly one validated transition"
                    )
                next_version = current_version + 1
                transition_payload = payload["transitions"][-1]
                connection.execute(
                    """
                    INSERT INTO model_lifecycle_transitions(
                        model_id, sequence, transition_json, idempotency_key
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(model_id),
                        next_version,
                        _json(transition_payload),
                        idempotency_key,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE model_registrations
                    SET registration_json = ?, lifecycle_status = ?,
                        evidence_level = ?, version = ?
                    WHERE model_id = ? AND version = ?
                    """,
                    (
                        _json(payload),
                        registration.lifecycle_status.value,
                        registration.evidence_level.value,
                        next_version,
                        str(model_id),
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError("model compare-and-swap failed")
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    aggregate_type="MODEL",
                    aggregate_id=str(model_id),
                    payload_hash=effective_hash,
                    result_version=next_version,
                )
                result = self._load_at(connection, model_id, next_version)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def _load_at(
        self,
        connection: sqlite3.Connection,
        model_id: ModelId,
        version: int,
    ) -> VersionedModelRegistration:
        row = _model_row(connection, model_id)
        current_version = int(row["version"])
        if version < 0 or version > current_version:
            raise ValueError("model command references an invalid result version")
        current_payload = _object_json(str(row["registration_json"]))
        current = model_registration_from_dict(current_payload)
        transition_rows = connection.execute(
            """
            SELECT transition_json FROM model_lifecycle_transitions
            WHERE model_id = ? AND sequence <= ? ORDER BY sequence
            """,
            (str(model_id), version),
        ).fetchall()
        transitions = tuple(
            model_transition_from_dict(
                _object_json(str(item["transition_json"]))
            )
            for item in transition_rows
        )
        status = (
            transitions[-1].to_status
            if transitions
            else ModelLifecycleStatus.DRAFT
        )
        evidence = (
            transitions[-1].evidence_level
            if transitions
            else EvidenceLevel.UNQUALIFIED
        )
        registration = ModelRegistration(
            definition=current.definition,
            lifecycle_status=status,
            evidence_level=evidence,
            transitions=transitions,
        )
        ModelRegistry().restore(registration)
        if version == current_version and registration != current:
            raise ValueError("stored model registration is not reconstructible")
        if row["definition_hash"] != registration.definition.definition_hash:
            raise ValueError("stored model definition hash mismatch")
        return VersionedModelRegistration(registration, version)


class SQLiteExperimentGovernanceRepository(_SQLiteGovernanceBase):
    """Frozen protocols with append-only access events and CAS counts."""

    def resolve_command(
        self,
        experiment_id: ExperimentId,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> VersionedExperimentGovernance | None:
        _key(idempotency_key)
        with self._connect() as connection:
            row = _command(connection, idempotency_key)
            if row is None:
                return None
            _validate_command(
                row,
                aggregate_type="EXPERIMENT",
                aggregate_id=str(experiment_id),
                payload_hash=command_hash,
            )
            return self._load_at(
                connection, experiment_id, int(row["result_version"])
            )

    def get(
        self, experiment_id: ExperimentId
    ) -> VersionedExperimentGovernance:
        with self._connect() as connection:
            row = _experiment_row(connection, experiment_id)
            return self._load_at(
                connection, experiment_id, int(row["version"])
            )

    def create(
        self,
        protocol: FrozenExperimentProtocol,
        *,
        idempotency_key: str,
    ) -> VersionedExperimentGovernance:
        _key(idempotency_key)
        ExperimentGovernance().register(protocol)
        payload = protocol.canonical_payload()
        command_hash = _payload_hash(payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(
                        command,
                        aggregate_type="EXPERIMENT",
                        aggregate_id=str(protocol.experiment_id),
                        payload_hash=command_hash,
                    )
                    result = self._load_at(
                        connection,
                        protocol.experiment_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                existing = connection.execute(
                    "SELECT * FROM governed_experiments WHERE experiment_id = ?",
                    (str(protocol.experiment_id),),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO governed_experiments(
                            experiment_id, protocol_json, protocol_hash, version
                        ) VALUES (?, ?, ?, 0)
                        """,
                        (
                            str(protocol.experiment_id),
                            _json(payload),
                            protocol.protocol_hash,
                        ),
                    )
                    version = 0
                else:
                    current = experiment_protocol_from_dict(
                        _object_json(str(existing["protocol_json"]))
                    )
                    if current != protocol:
                        raise ValueError("experiment identity conflict")
                    version = int(existing["version"])
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    aggregate_type="EXPERIMENT",
                    aggregate_id=str(protocol.experiment_id),
                    payload_hash=command_hash,
                    result_version=version,
                )
                result = self._load_at(
                    connection, protocol.experiment_id, version
                )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def append_access(
        self,
        experiment_id: ExperimentId,
        *,
        expected_version: int,
        access_kind: str,
        access_record: ExperimentAccessRecord,
        idempotency_key: str,
        command_hash: str | None = None,
    ) -> VersionedExperimentGovernance:
        _key(idempotency_key)
        if access_kind not in {"VALIDATION", "SEALED_TEST"}:
            raise ValueError("unsupported experiment access kind")
        effective_hash = command_hash or _payload_hash(
            {
                "experiment_id": str(experiment_id),
                "access_kind": access_kind,
                "access_record": {
                    "validation": access_record.validation_access_count,
                    "sealed": access_record.sealed_test_access_count,
                },
            }
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                command = _command(connection, idempotency_key)
                if command is not None:
                    _validate_command(
                        command,
                        aggregate_type="EXPERIMENT",
                        aggregate_id=str(experiment_id),
                        payload_hash=effective_hash,
                    )
                    result = self._load_at(
                        connection,
                        experiment_id,
                        int(command["result_version"]),
                    )
                    connection.commit()
                    return result
                row = _experiment_row(connection, experiment_id)
                current_version = int(row["version"])
                if current_version != expected_version:
                    raise VersionConflictError(
                        f"experiment {experiment_id} expected version "
                        f"{expected_version}, found {current_version}"
                    )
                current = self._load_at(
                    connection, experiment_id, current_version
                )
                governance = _domain_from_experiment(current)
                expected_record = (
                    governance.record_validation_access(experiment_id)
                    if access_kind == "VALIDATION"
                    else governance.record_sealed_test_access(experiment_id)
                )
                if expected_record != access_record:
                    raise ValueError(
                        "experiment access does not match validated domain result"
                    )
                next_version = current_version + 1
                connection.execute(
                    """
                    INSERT INTO experiment_access_events(
                        experiment_id, sequence, access_kind,
                        validation_access_count, sealed_test_access_count,
                        idempotency_key
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(experiment_id),
                        next_version,
                        access_kind,
                        access_record.validation_access_count,
                        access_record.sealed_test_access_count,
                        idempotency_key,
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE governed_experiments
                    SET validation_access_count = ?,
                        sealed_test_access_count = ?, version = ?
                    WHERE experiment_id = ? AND version = ?
                    """,
                    (
                        access_record.validation_access_count,
                        access_record.sealed_test_access_count,
                        next_version,
                        str(experiment_id),
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError(
                        "experiment compare-and-swap failed"
                    )
                _insert_command(
                    connection,
                    idempotency_key=idempotency_key,
                    aggregate_type="EXPERIMENT",
                    aggregate_id=str(experiment_id),
                    payload_hash=effective_hash,
                    result_version=next_version,
                )
                result = self._load_at(
                    connection, experiment_id, next_version
                )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def _load_at(
        self,
        connection: sqlite3.Connection,
        experiment_id: ExperimentId,
        version: int,
    ) -> VersionedExperimentGovernance:
        row = _experiment_row(connection, experiment_id)
        current_version = int(row["version"])
        if version < 0 or version > current_version:
            raise ValueError(
                "experiment command references an invalid result version"
            )
        protocol = experiment_protocol_from_dict(
            _object_json(str(row["protocol_json"]))
        )
        governance = ExperimentGovernance()
        governance.register(protocol)
        events = connection.execute(
            """
            SELECT * FROM experiment_access_events
            WHERE experiment_id = ? AND sequence <= ? ORDER BY sequence
            """,
            (str(experiment_id), version),
        ).fetchall()
        for sequence, event in enumerate(events, start=1):
            if int(event["sequence"]) != sequence:
                raise ValueError("experiment access history has a sequence gap")
            record = (
                governance.record_validation_access(experiment_id)
                if event["access_kind"] == "VALIDATION"
                else governance.record_sealed_test_access(experiment_id)
            )
            if (
                record.validation_access_count
                != int(event["validation_access_count"])
                or record.sealed_test_access_count
                != int(event["sealed_test_access_count"])
            ):
                raise ValueError(
                    "experiment access history is not reconstructible"
                )
        access = governance.access_record(experiment_id)
        if version == current_version and (
            access.validation_access_count
            != int(row["validation_access_count"])
            or access.sealed_test_access_count
            != int(row["sealed_test_access_count"])
        ):
            raise ValueError("stored experiment access counts mismatch")
        if protocol.protocol_hash != row["protocol_hash"]:
            raise ValueError("stored experiment protocol hash mismatch")
        return VersionedExperimentGovernance(protocol, access, version)


def _domain_from_experiment(
    versioned: VersionedExperimentGovernance,
) -> ExperimentGovernance:
    governance = ExperimentGovernance()
    experiment_id = governance.register(versioned.protocol)
    for _ in range(versioned.access_record.validation_access_count):
        governance.record_validation_access(experiment_id)
    for _ in range(versioned.access_record.sealed_test_access_count):
        governance.record_sealed_test_access(experiment_id)
    return governance


def _model_row(
    connection: sqlite3.Connection, model_id: ModelId
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM model_registrations WHERE model_id = ?",
        (str(model_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(model_id))
    return row


def _experiment_row(
    connection: sqlite3.Connection, experiment_id: ExperimentId
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM governed_experiments WHERE experiment_id = ?",
        (str(experiment_id),),
    ).fetchone()
    if row is None:
        raise KeyError(str(experiment_id))
    return row


def _command(
    connection: sqlite3.Connection, idempotency_key: str
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM governance_commands WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()


def _validate_command(
    row: sqlite3.Row,
    *,
    aggregate_type: str,
    aggregate_id: str,
    payload_hash: str,
) -> None:
    if (
        row["aggregate_type"] != aggregate_type
        or row["aggregate_id"] != aggregate_id
        or row["payload_hash"] != payload_hash
    ):
        raise ValueError("idempotency key was reused for a different command")


def _insert_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    aggregate_type: str,
    aggregate_id: str,
    payload_hash: str,
    result_version: int,
) -> None:
    connection.execute(
        """
        INSERT INTO governance_commands(
            idempotency_key, aggregate_type, aggregate_id, payload_hash,
            result_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            idempotency_key,
            aggregate_type,
            aggregate_id,
            payload_hash,
            result_version,
            datetime.now(UTC).isoformat(),
        ),
    )


def _key(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("idempotency_key must be a non-empty trimmed string")


def _json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload_hash(payload: Any) -> str:
    return f"sha256:{sha256(_json(payload).encode('utf-8')).hexdigest()}"


def _object_json(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("stored governance JSON must contain an object")
    return payload
