"""Append-only SQLite publication, command and replay index for H6."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any

from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionPolicy,
    CompositeOperationalInputManifest,
    CompositeOperationalManifestBuilder,
)
from market_regime_alpha.application.operational_research.composite_repository import (
    composite_operational_command_hash,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    require_sha256,
    require_text,
)


_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
COMPOSITE_OPERATIONAL_UP_MIGRATION = (
    _MIGRATION_ROOT / "009_composite_operational_evidence_up.sql"
)
COMPOSITE_OPERATIONAL_DOWN_MIGRATION = (
    _MIGRATION_ROOT / "009_composite_operational_evidence_down.sql"
)

_TABLE_COLUMNS = {
    "composite_operational_manifests": (
        "manifest_id",
        "content_hash",
        "status",
        "decision_time",
        "created_at",
        "policy_id",
        "policy_hash",
        "builder_revision",
        "package_path",
        "daily_package_path",
        "supplemental_package_path",
        "artifact_json",
        "policy_json",
    ),
    "composite_operational_components": (
        "manifest_id",
        "role",
        "scope_key",
        "artifact_id",
        "content_hash",
        "source_manifest_id",
        "source_manifest_hash",
        "availability_time",
        "data_eligibility",
    ),
    "composite_operational_field_authorities": (
        "manifest_id",
        "field_group",
        "scope_key",
        "component_role",
        "artifact_id",
        "content_hash",
    ),
    "composite_operational_commands": (
        "idempotency_key",
        "command_hash",
        "manifest_id",
        "command_json",
        "created_at",
    ),
}

_FOREIGN_KEYS = {
    "composite_operational_manifests": set(),
    "composite_operational_components": {
        (
            "composite_operational_manifests",
            "manifest_id",
            "manifest_id",
        )
    },
    "composite_operational_field_authorities": {
        (
            "composite_operational_manifests",
            "manifest_id",
            "manifest_id",
        )
    },
    "composite_operational_commands": {
        (
            "composite_operational_manifests",
            "manifest_id",
            "manifest_id",
        )
    },
}

_TRIGGER_MESSAGES = {
    "composite_operational_manifests_no_update": (
        "composite operational manifests are append-only"
    ),
    "composite_operational_manifests_no_delete": (
        "composite operational manifests are append-only"
    ),
    "composite_operational_components_no_update": (
        "composite operational components are append-only"
    ),
    "composite_operational_components_no_delete": (
        "composite operational components are append-only"
    ),
    "composite_operational_field_authorities_no_update": (
        "composite operational field authorities are append-only"
    ),
    "composite_operational_field_authorities_no_delete": (
        "composite operational field authorities are append-only"
    ),
    "composite_operational_commands_no_update": (
        "composite operational commands are append-only"
    ),
    "composite_operational_commands_no_delete": (
        "composite operational commands are append-only"
    ),
}


class SQLiteCompositeOperationalRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                COMPOSITE_OPERATIONAL_UP_MIGRATION.read_text(encoding="utf-8")
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

    def save_manifest(
        self,
        composite: VerifiedCompositeOperationalManifest,
        *,
        daily_package_path: Path,
        supplemental_package_path: Path,
        idempotency_key: str,
        command_hash: str,
        before_command_insert: Callable[[], None] | None = None,
    ) -> VerifiedCompositeOperationalManifest:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        verified = load_verified_composite_operational_manifest(composite.root)
        daily = load_verified_daily_decision_artifact(daily_package_path)
        supplemental = load_verified_supplemental_research_evidence(
            supplemental_package_path
        )
        expected_command_hash = composite_operational_command_hash(
            daily=daily,
            supplemental=supplemental,
            composite=verified,
        )
        if command_hash != expected_command_hash:
            raise ValueError("composite operational command hash mismatch")
        _replay_builder(verified, daily.root, supplemental.root)
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
                row = connection.execute(
                    """
                    SELECT * FROM composite_operational_manifests
                    WHERE manifest_id = ? OR content_hash = ?
                    """,
                    (
                        str(verified.manifest.manifest_id),
                        verified.manifest.content_hash,
                    ),
                ).fetchone()
                if row is None:
                    _insert_manifest(
                        connection,
                        verified,
                        daily_path=daily.root,
                        supplemental_path=supplemental.root,
                    )
                else:
                    existing = _restore_row(connection, row)
                    if existing != verified:
                        raise ValueError(
                            "Composite Operational Manifest identity conflict"
                        )
                if before_command_insert is not None:
                    before_command_insert()
                connection.execute(
                    """
                    INSERT INTO composite_operational_commands(
                        idempotency_key, command_hash, manifest_id,
                        command_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        idempotency_key,
                        command_hash,
                        str(verified.manifest.manifest_id),
                        _json(
                            _command_projection(
                                idempotency_key=idempotency_key,
                                command_hash=command_hash,
                                composite=verified,
                            )
                        ),
                        canonical_datetime(verified.manifest.created_at),
                    ),
                )
                stored = _load_manifest(
                    connection, verified.manifest.manifest_id
                )
                connection.commit()
                return stored
            except Exception:
                connection.rollback()
                raise

    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> VerifiedCompositeOperationalManifest | None:
        _key(idempotency_key)
        require_sha256("command_hash", command_hash)
        with self._connect() as connection:
            return _resolve_command(
                connection,
                idempotency_key=idempotency_key,
                command_hash=command_hash,
            )

    def get_manifest(
        self, manifest_id: ArtifactId
    ) -> VerifiedCompositeOperationalManifest:
        with self._connect() as connection:
            return _load_manifest(connection, manifest_id)

    def get_source_package_paths(
        self, manifest_id: ArtifactId
    ) -> tuple[Path, Path]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT daily_package_path, supplemental_package_path
                FROM composite_operational_manifests WHERE manifest_id = ?
                """,
                (str(manifest_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown Composite Operational Manifest: {manifest_id}")
            return (
                Path(str(row["daily_package_path"])).resolve(),
                Path(str(row["supplemental_package_path"])).resolve(),
            )


def _insert_manifest(
    connection: sqlite3.Connection,
    composite: VerifiedCompositeOperationalManifest,
    *,
    daily_path: Path,
    supplemental_path: Path,
) -> None:
    manifest = composite.manifest
    policy = composite.composition_policy
    connection.execute(
        """
        INSERT INTO composite_operational_manifests(
            manifest_id, content_hash, status, decision_time, created_at,
            policy_id, policy_hash, builder_revision, package_path,
            daily_package_path, supplemental_package_path, artifact_json,
            policy_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(manifest.manifest_id),
            manifest.content_hash,
            manifest.status.value,
            canonical_datetime(manifest.decision_time.value),
            canonical_datetime(manifest.created_at),
            str(policy.policy_id),
            policy.policy_hash,
            policy.builder_revision,
            str(composite.root.resolve()),
            str(daily_path.resolve()),
            str(supplemental_path.resolve()),
            _json(manifest.to_canonical_dict()),
            _json(policy.to_canonical_dict()),
        ),
    )
    connection.executemany(
        """
        INSERT INTO composite_operational_components(
            manifest_id, role, scope_key, artifact_id, content_hash,
            source_manifest_id, source_manifest_hash, availability_time,
            data_eligibility
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                str(manifest.manifest_id),
                item.role.value,
                item.scope_key,
                str(item.artifact_id),
                item.content_hash,
                str(item.source_manifest_id),
                item.source_manifest_hash,
                canonical_datetime(item.availability_time.value),
                item.data_eligibility.value,
            )
            for item in manifest.component_references
        ),
    )
    connection.executemany(
        """
        INSERT INTO composite_operational_field_authorities(
            manifest_id, field_group, scope_key, component_role,
            artifact_id, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                str(manifest.manifest_id),
                item.field_group.value,
                item.scope_key,
                item.component_role.value,
                str(item.artifact_id),
                item.content_hash,
            )
            for item in manifest.field_authority_references
        ),
    )


def _resolve_command(
    connection: sqlite3.Connection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> VerifiedCompositeOperationalManifest | None:
    row = connection.execute(
        "SELECT * FROM composite_operational_commands WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    if row["command_hash"] != command_hash:
        raise ValueError(
            "idempotency key reused for a different composite operational command"
        )
    composite = _load_manifest(
        connection, ArtifactId(str(row["manifest_id"]))
    )
    manifest_row = connection.execute(
        """
        SELECT daily_package_path, supplemental_package_path
        FROM composite_operational_manifests WHERE manifest_id = ?
        """,
        (str(composite.manifest.manifest_id),),
    ).fetchone()
    assert manifest_row is not None
    daily = load_verified_daily_decision_artifact(
        Path(str(manifest_row["daily_package_path"]))
    )
    supplemental = load_verified_supplemental_research_evidence(
        Path(str(manifest_row["supplemental_package_path"]))
    )
    expected_hash = composite_operational_command_hash(
        daily=daily,
        supplemental=supplemental,
        composite=composite,
    )
    expected_projection = _command_projection(
        idempotency_key=idempotency_key,
        command_hash=expected_hash,
        composite=composite,
    )
    if (
        expected_hash != row["command_hash"]
        or _object_json(str(row["command_json"])) != expected_projection
        or row["created_at"] != canonical_datetime(composite.manifest.created_at)
    ):
        raise ValueError("composite operational command projection mismatch")
    return composite


def _load_manifest(
    connection: sqlite3.Connection,
    manifest_id: ArtifactId,
) -> VerifiedCompositeOperationalManifest:
    row = connection.execute(
        "SELECT * FROM composite_operational_manifests WHERE manifest_id = ?",
        (str(manifest_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Composite Operational Manifest: {manifest_id}")
    return _restore_row(connection, row)


def _restore_row(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> VerifiedCompositeOperationalManifest:
    policy = CompositeOperationalCompositionPolicy.from_canonical_dict(
        _object_json(str(row["policy_json"]))
    )
    manifest = CompositeOperationalInputManifest.from_canonical_dict(
        _object_json(str(row["artifact_json"])),
        composition_policy=policy,
    )
    package = load_verified_composite_operational_manifest(
        Path(str(row["package_path"]))
    )
    if package.manifest != manifest or package.composition_policy != policy:
        raise ValueError("composite operational package projection mismatch")
    if not (
        row["manifest_id"] == str(manifest.manifest_id)
        and row["content_hash"] == manifest.content_hash
        and row["status"] == manifest.status.value
        and row["decision_time"] == canonical_datetime(manifest.decision_time.value)
        and row["created_at"] == canonical_datetime(manifest.created_at)
        and row["policy_id"] == str(policy.policy_id)
        and row["policy_hash"] == policy.policy_hash
        and row["builder_revision"] == policy.builder_revision
    ):
        raise ValueError("composite operational manifest projection mismatch")
    component_rows = connection.execute(
        """
        SELECT role, scope_key, artifact_id, content_hash, source_manifest_id,
               source_manifest_hash, availability_time, data_eligibility
        FROM composite_operational_components WHERE manifest_id = ?
        ORDER BY role, scope_key
        """,
        (str(manifest.manifest_id),),
    ).fetchall()
    expected_components = tuple(
        (
            item.role.value,
            item.scope_key,
            str(item.artifact_id),
            item.content_hash,
            str(item.source_manifest_id),
            item.source_manifest_hash,
            canonical_datetime(item.availability_time.value),
            item.data_eligibility.value,
        )
        for item in manifest.component_references
    )
    actual_components = tuple(tuple(value for value in item) for item in component_rows)
    if actual_components != expected_components:
        raise ValueError("composite operational component projection mismatch")
    field_rows = connection.execute(
        """
        SELECT field_group, scope_key, component_role, artifact_id, content_hash
        FROM composite_operational_field_authorities WHERE manifest_id = ?
        ORDER BY field_group, scope_key
        """,
        (str(manifest.manifest_id),),
    ).fetchall()
    expected_fields = tuple(
        (
            item.field_group.value,
            item.scope_key,
            item.component_role.value,
            str(item.artifact_id),
            item.content_hash,
        )
        for item in manifest.field_authority_references
    )
    actual_fields = tuple(tuple(value for value in item) for item in field_rows)
    if actual_fields != expected_fields:
        raise ValueError("composite operational field authority projection mismatch")
    _replay_builder(
        package,
        Path(str(row["daily_package_path"])),
        Path(str(row["supplemental_package_path"])),
    )
    return package


def _replay_builder(
    composite: VerifiedCompositeOperationalManifest,
    daily_path: Path,
    supplemental_path: Path,
) -> None:
    daily = load_verified_daily_decision_artifact(daily_path)
    supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    replayed = CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental,
        composition_policy=composite.composition_policy,
        created_at=composite.manifest.created_at,
    )
    if replayed != composite.manifest:
        raise ValueError("Composite Operational Manifest Builder replay mismatch")


def _command_projection(
    *,
    idempotency_key: str,
    command_hash: str,
    composite: VerifiedCompositeOperationalManifest,
) -> dict[str, str]:
    return {
        "schema_version": "composite-operational-command-index-v1",
        "idempotency_key": idempotency_key,
        "command_hash": command_hash,
        "manifest_id": str(composite.manifest.manifest_id),
        "manifest_hash": composite.manifest.content_hash,
    }


def _validate_schema(connection: sqlite3.Connection) -> None:
    if connection.execute(
        "SELECT 1 FROM pdl_schema_migrations WHERE version = 9"
    ).fetchone() is None:
        raise ValueError("composite operational migration 009 is not applied")
    for table, columns in _TABLE_COLUMNS.items():
        actual_columns = tuple(
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        if actual_columns != columns:
            raise ValueError(f"composite operational table schema mismatch: {table}")
        actual_foreign_keys = {
            (str(row["table"]), str(row["from"]), str(row["to"]))
            for row in connection.execute(f"PRAGMA foreign_key_list({table})")
        }
        if actual_foreign_keys != _FOREIGN_KEYS[table]:
            raise ValueError(f"composite operational foreign key mismatch: {table}")
    manifest_sql = _normalized_sql(
        connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'composite_operational_manifests'
            """
        ).fetchone()["sql"]
    )
    component_sql = _normalized_sql(
        connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'composite_operational_components'
            """
        ).fetchone()["sql"]
    )
    if "check(statusin('verified','data_insufficient','conflicted'))" not in manifest_sql:
        raise ValueError("composite operational status constraint mismatch")
    if "check(data_eligibility='exploratory')" not in component_sql:
        raise ValueError("composite operational eligibility constraint mismatch")
    for name, message in _TRIGGER_MESSAGES.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (name,),
        ).fetchone()
        if row is None:
            raise ValueError("composite operational append-only trigger is missing")
        sql = str(row["sql"]).lower()
        operation = "update" if name.endswith("no_update") else "delete"
        if (
            f"before {operation}" not in sql
            or "raise(abort" not in sql.replace(" ", "")
            or message not in sql
        ):
            raise ValueError("composite operational append-only trigger mismatch")


def _key(value: str) -> None:
    require_text("idempotency_key", value)


def _json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _object_json(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid composite operational repository JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("composite operational repository JSON must be an object")
    return payload


def _normalized_sql(value: object) -> str:
    return "".join(str(value).lower().split())
