"""Append-only native PostgreSQL publication, command and replay index for H6."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
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
    require_sha256,
    require_text,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.native_repository import (
    NativePostgresRepository,
    PostgresConnection,
    acquire_scope_lock,
    aware_datetime,
)


class PostgresCompositeOperationalRepository(NativePostgresRepository):
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        super().__init__(factory)

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
            try:
                acquire_scope_lock(
                    connection,
                    namespace="composite-operational-manifest",
                    identity=str(composite.manifest.manifest_id),
                )
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
                    WHERE manifest_id = %s OR content_hash = %s
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
                    ) VALUES (%s, %s, %s, %s, %s)
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
                        verified.manifest.created_at,
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
                FROM composite_operational_manifests WHERE manifest_id = %s
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
    connection: PostgresConnection,
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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(manifest.manifest_id),
            manifest.content_hash,
            manifest.status.value,
            manifest.decision_time.value,
            manifest.created_at,
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
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO composite_operational_components(
                manifest_id, role, scope_key, artifact_id, content_hash,
                source_manifest_id, source_manifest_hash, availability_time,
                data_eligibility
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    item.availability_time.value,
                    item.data_eligibility.value,
                )
                for item in manifest.component_references
            ),
        )
        cursor.executemany(
            """
            INSERT INTO composite_operational_field_authorities(
                manifest_id, field_group, scope_key, component_role,
                artifact_id, content_hash
            ) VALUES (%s, %s, %s, %s, %s, %s)
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
    connection: PostgresConnection,
    *,
    idempotency_key: str,
    command_hash: str,
) -> VerifiedCompositeOperationalManifest | None:
    row = connection.execute(
        "SELECT * FROM composite_operational_commands WHERE idempotency_key = %s",
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
        FROM composite_operational_manifests WHERE manifest_id = %s
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
        or aware_datetime(row["created_at"], label="created_at")
        != composite.manifest.created_at
    ):
        raise ValueError("composite operational command projection mismatch")
    return composite


def _load_manifest(
    connection: PostgresConnection,
    manifest_id: ArtifactId,
) -> VerifiedCompositeOperationalManifest:
    row = connection.execute(
        "SELECT * FROM composite_operational_manifests WHERE manifest_id = %s",
        (str(manifest_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"unknown Composite Operational Manifest: {manifest_id}")
    return _restore_row(connection, row)


def _restore_row(
    connection: PostgresConnection,
    row: dict[str, Any],
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
        and aware_datetime(row["decision_time"], label="decision_time")
        == manifest.decision_time.value
        and aware_datetime(row["created_at"], label="created_at")
        == manifest.created_at
        and row["policy_id"] == str(policy.policy_id)
        and row["policy_hash"] == policy.policy_hash
        and row["builder_revision"] == policy.builder_revision
    ):
        raise ValueError("composite operational manifest projection mismatch")
    component_rows = connection.execute(
        """
        SELECT role, scope_key, artifact_id, content_hash, source_manifest_id,
               source_manifest_hash, availability_time, data_eligibility
        FROM composite_operational_components WHERE manifest_id = %s
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
            item.availability_time.value,
            item.data_eligibility.value,
        )
        for item in manifest.component_references
    )
    actual_components = tuple(
        (
            item["role"],
            item["scope_key"],
            item["artifact_id"],
            item["content_hash"],
            item["source_manifest_id"],
            item["source_manifest_hash"],
            aware_datetime(item["availability_time"], label="availability_time"),
            item["data_eligibility"],
        )
        for item in component_rows
    )
    if actual_components != expected_components:
        raise ValueError("composite operational component projection mismatch")
    field_rows = connection.execute(
        """
        SELECT field_group, scope_key, component_role, artifact_id, content_hash
        FROM composite_operational_field_authorities WHERE manifest_id = %s
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
    actual_fields = tuple(
        (
            item["field_group"],
            item["scope_key"],
            item["component_role"],
            item["artifact_id"],
            item["content_hash"],
        )
        for item in field_rows
    )
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


__all__ = ["PostgresCompositeOperationalRepository"]
