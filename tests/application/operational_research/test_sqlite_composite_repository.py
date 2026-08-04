from __future__ import annotations

from datetime import timedelta
import sqlite3
from pathlib import Path

import pytest

from market_regime_alpha.application.operational_research.composite_artifact import (
    load_verified_composite_operational_manifest,
    publish_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalManifestBuilder,
)
from market_regime_alpha.application.operational_research.composite_repository import (
    composite_operational_command_hash,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    COMPOSITE_OPERATIONAL_DOWN_MIGRATION,
    COMPOSITE_OPERATIONAL_UP_MIGRATION,
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
    publish_supplemental_research_evidence,
)
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _policy,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _publication(tmp_path: Path, fixture: DailyDecisionFixture):
    daily_path = publish_phase_d_daily_decision_artifact(
        root=tmp_path / "daily", bundle=_daily_bundle(fixture)
    )
    supplemental_path = publish_supplemental_research_evidence(
        root=tmp_path / "supplemental", bundle=_supplemental(fixture)
    )
    daily = load_verified_daily_decision_artifact(daily_path)
    supplemental = load_verified_supplemental_research_evidence(
        supplemental_path
    )
    manifest = CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental,
        composition_policy=_policy(),
        created_at=daily.bundle.source_manifest.decision_time.value
        + timedelta(minutes=10),
    )
    package_path = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=manifest,
        composition_policy=_policy(),
    )
    verified = load_verified_composite_operational_manifest(package_path)
    command_hash = composite_operational_command_hash(
        daily=daily,
        supplemental=supplemental,
        composite=verified,
    )
    return daily_path, supplemental_path, verified, command_hash


def test_migration_009_is_repeat_safe_and_has_isolated_down_path(
    tmp_path: Path,
) -> None:
    path = tmp_path / "migration.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            COMPOSITE_OPERATIONAL_UP_MIGRATION.read_text(encoding="utf-8")
        )
        connection.executescript(
            COMPOSITE_OPERATIONAL_UP_MIGRATION.read_text(encoding="utf-8")
        )
        assert connection.execute(
            "SELECT 1 FROM pdl_schema_migrations WHERE version = 9"
        ).fetchone() == (1,)
        connection.executescript(
            COMPOSITE_OPERATIONAL_DOWN_MIGRATION.read_text(encoding="utf-8")
        )
        assert connection.execute(
            "SELECT 1 FROM pdl_schema_migrations WHERE version = 9"
        ).fetchone() is None
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'composite_operational_%'"
        ).fetchall() == []


def test_repository_save_read_restart_and_same_command_replay(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    database = tmp_path / "authority.sqlite3"
    repository = SQLiteCompositeOperationalRepository(database)

    first = repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-1",
        command_hash=command_hash,
    )
    second = repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-1",
        command_hash=command_hash,
    )
    restarted = SQLiteCompositeOperationalRepository(database)

    assert first == second == verified
    assert restarted.get_manifest(verified.manifest.manifest_id) == verified
    assert restarted.resolve_command(
        idempotency_key="h6-command-1", command_hash=command_hash
    ) == verified
    assert restarted.get_source_package_paths(
        verified.manifest.manifest_id
    ) == (daily_path.resolve(), supplemental_path.resolve())


def test_repository_rejects_idempotency_conflict_and_projection_tamper(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    database = tmp_path / "authority.sqlite3"
    repository = SQLiteCompositeOperationalRepository(database)
    repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-1",
        command_hash=command_hash,
    )

    with pytest.raises(ValueError, match="idempotency key"):
        repository.resolve_command(
            idempotency_key="h6-command-1",
            command_hash="sha256:" + "9" * 64,
        )

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DROP TRIGGER composite_operational_components_no_update"
        )
        connection.execute(
            """
            UPDATE composite_operational_components
            SET content_hash = ?
            WHERE rowid = (
                SELECT rowid
                FROM composite_operational_components
                ORDER BY manifest_id, role, scope_key
                LIMIT 1
            )
            """,
            ("sha256:" + "8" * 64,),
        )
    with pytest.raises(ValueError, match="component projection"):
        repository.get_manifest(verified.manifest.manifest_id)


@pytest.mark.parametrize(
    ("table", "trigger", "assignment", "expected"),
    [
        (
            "composite_operational_field_authorities",
            "composite_operational_field_authorities_no_update",
            "content_hash = 'sha256:8888888888888888888888888888888888888888888888888888888888888888'",
            "field authority projection",
        ),
        (
            "composite_operational_commands",
            "composite_operational_commands_no_update",
            "command_json = '{}'",
            "command projection",
        ),
        (
            "composite_operational_manifests",
            "composite_operational_manifests_no_update",
            "artifact_json = '{}'",
            "manifest fields mismatch",
        ),
        (
            "composite_operational_manifests",
            "composite_operational_manifests_no_update",
            "policy_json = '{}'",
            "policy fields mismatch",
        ),
    ],
)
def test_repository_rejects_projection_and_canonical_json_tamper(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    table: str,
    trigger: str,
    assignment: str,
    expected: str,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    database = tmp_path / "authority.sqlite3"
    repository = SQLiteCompositeOperationalRepository(database)
    repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-tamper",
        command_hash=command_hash,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(f"UPDATE {table} SET {assignment}")

    def operation() -> object:
        if table == "composite_operational_commands":
            return repository.resolve_command(
                idempotency_key="h6-command-tamper",
                command_hash=command_hash,
            )
        return repository.get_manifest(verified.manifest.manifest_id)

    with pytest.raises(ValueError, match=expected):
        operation()


def test_repository_fails_closed_when_indexed_package_is_missing(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    repository = SQLiteCompositeOperationalRepository(
        tmp_path / "authority.sqlite3"
    )
    repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-missing-package",
        command_hash=command_hash,
    )
    verified.root.rename(tmp_path / "package-detached-for-test")

    with pytest.raises(ValueError, match="package is missing"):
        repository.get_manifest(verified.manifest.manifest_id)


def test_repository_rejects_weak_schema_and_spoofed_trigger(
    tmp_path: Path,
) -> None:
    weak_database = tmp_path / "weak.sqlite3"
    with sqlite3.connect(weak_database) as connection:
        connection.executescript(
            """
            CREATE TABLE pdl_schema_migrations(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO pdl_schema_migrations VALUES(9, CURRENT_TIMESTAMP);
            CREATE TABLE composite_operational_manifests(manifest_id TEXT);
            """
        )
    with pytest.raises(ValueError, match="table schema mismatch"):
        SQLiteCompositeOperationalRepository(weak_database)

    spoofed_database = tmp_path / "spoofed.sqlite3"
    SQLiteCompositeOperationalRepository(spoofed_database)
    with sqlite3.connect(spoofed_database) as connection:
        connection.executescript(
            """
            DROP TRIGGER composite_operational_commands_no_update;
            CREATE TRIGGER composite_operational_commands_no_update
            BEFORE UPDATE ON composite_operational_commands
            BEGIN
                SELECT 1;
            END;
            """
        )
    with pytest.raises(ValueError, match="append-only trigger mismatch"):
        SQLiteCompositeOperationalRepository(spoofed_database)


@pytest.mark.parametrize(
    "table",
    [
        "composite_operational_manifests",
        "composite_operational_components",
        "composite_operational_field_authorities",
        "composite_operational_commands",
    ],
)
def test_migration_009_tables_are_append_only(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    table: str,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    database = tmp_path / "authority.sqlite3"
    repository = SQLiteCompositeOperationalRepository(database)
    repository.save_manifest(
        verified,
        daily_package_path=daily_path,
        supplemental_package_path=supplemental_path,
        idempotency_key="h6-command-1",
        command_hash=command_hash,
    )
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(f"DELETE FROM {table}")


def test_transaction_failure_rolls_back_all_manifest_projections(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    daily_path, supplemental_path, verified, command_hash = _publication(
        tmp_path, daily_decision_fixture
    )
    database = tmp_path / "authority.sqlite3"
    repository = SQLiteCompositeOperationalRepository(database)

    with pytest.raises(RuntimeError, match="injected"):
        repository.save_manifest(
            verified,
            daily_package_path=daily_path,
            supplemental_package_path=supplemental_path,
            idempotency_key="h6-command-rollback",
            command_hash=command_hash,
            before_command_insert=lambda: (_ for _ in ()).throw(
                RuntimeError("injected before command insert")
            ),
        )

    with sqlite3.connect(database) as connection:
        for table in (
            "composite_operational_manifests",
            "composite_operational_components",
            "composite_operational_field_authorities",
            "composite_operational_commands",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone() == (0,)
