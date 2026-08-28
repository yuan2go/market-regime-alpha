from __future__ import annotations

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_FOUNDATION_TABLES,
    SCHEMA_EPOCH,
    CatalogDriftError,
    LegacySchemaPresentError,
    RecreateAuthorization,
    RecreatePlan,
    RecreatePlanStaleError,
    SchemaChecksumMismatchError,
    SchemaEpochMismatchError,
    SchemaManager,
    SchemaMissingError,
    UnexpectedCatalogError,
    UnsafeRecreateError,
)


def test_empty_database_bootstrap_retry_and_verify(target_database_url: str) -> None:
    manager = SchemaManager(target_database_url)

    created = manager.bootstrap()
    retried = manager.bootstrap()
    verified = manager.verify()

    assert created.created is True
    assert retried.created is False
    assert verified.created is False
    assert verified.epoch == SCHEMA_EPOCH
    assert verified.schema_name == "mra"
    assert verified.release_state == "DRAFT"
    assert verified.baseline_version == 1
    assert verified.tables == EXPECTED_FOUNDATION_TABLES
    assert len(verified.baseline_checksum) == 64
    assert len(verified.seed_checksum) == 64
    assert len(verified.catalog_checksum) == 64
    assert len(verified.reference_vocabulary_checksum) == 64


def test_normal_verify_fails_closed_without_creating_schema(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)

    with pytest.raises(SchemaMissingError, match="SCHEMA_MISSING"):
        manager.verify()

    with psycopg.connect(target_database_url) as connection:
        exists = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mra')"
        ).fetchone()
    assert exists == (False,)


def test_bootstrap_rejects_recognized_legacy_catalog_before_ddl(
    target_database_url: str,
) -> None:
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("CREATE TABLE public.continuous_research_run (id uuid PRIMARY KEY)")

    with pytest.raises(LegacySchemaPresentError, match="LEGACY_SCHEMA_PRESENT"):
        SchemaManager(target_database_url).bootstrap()

    with psycopg.connect(target_database_url) as connection:
        exists = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mra')"
        ).fetchone()
    assert exists == (False,)


def test_bootstrap_rejects_unknown_user_catalog_before_ddl(
    target_database_url: str,
) -> None:
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("CREATE TABLE public.unexpected_probe (id bigint PRIMARY KEY)")

    with pytest.raises(UnexpectedCatalogError, match="UNEXPECTED_CATALOG_OBJECTS"):
        SchemaManager(target_database_url).bootstrap()


def test_verify_rejects_checksum_and_unexpected_object_drift(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    manager.bootstrap()

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.schema_epoch SET baseline_checksum = %s",
            ("0" * 64,),
        )
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")

    with pytest.raises(SchemaChecksumMismatchError, match="BASELINE_CHECKSUM_MISMATCH"):
        manager.verify()

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.schema_epoch SET baseline_checksum = %s",
            (manager.baseline_checksum,),
        )
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")
        connection.execute("CREATE TABLE mra.unexpected_probe (id bigint PRIMARY KEY)")

    with pytest.raises(CatalogDriftError, match="CATALOG_DRIFT"):
        manager.verify()


def test_verify_rejects_vocabulary_and_disabled_trigger_drift(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    manager.bootstrap()

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.schema_epoch SET reference_vocabulary_checksum = %s",
            ("0" * 64,),
        )
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")

    with pytest.raises(
        SchemaChecksumMismatchError,
        match="REFERENCE_VOCABULARY_CHECKSUM_MISMATCH",
    ):
        manager.verify()

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.schema_epoch SET reference_vocabulary_checksum = %s",
            (manager.reference_vocabulary_checksum,),
        )
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")
        connection.execute(
            "ALTER TABLE mra.audit_event DISABLE TRIGGER audit_event_append_only"
        )

    with pytest.raises(CatalogDriftError, match="CATALOG_DRIFT"):
        manager.verify()


def test_recreate_plan_is_bound_to_database_oid_catalog_and_challenge(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url, recreate_plan_ttl=timedelta(minutes=5))
    before = manager.bootstrap()
    identity = manager.database_identity()
    authorization = RecreateAuthorization(
        expected_database_name=identity.database_name,
        expected_database_oid=identity.database_oid,
        operator_id="foundation-test",
        reason="exercise an isolated target draft recreate",
        backup_attestation="isolated disposable test database; no business data",
    )
    plan = manager.plan_recreate(authorization)
    assert RecreatePlan.from_json(plan.to_json()) == plan
    assert plan.schema_owner == identity.connected_role
    assert plan.active_connection_pids == ()
    assert plan.unexpected_objects == ()
    assert "schema:mra" in plan.catalog_objects

    with pytest.raises(RecreatePlanStaleError, match="RECREATE_CHALLENGE_MISMATCH"):
        manager.apply_recreate(
            plan,
            challenge="wrong",
            operator_id=authorization.operator_id,
        )

    with pytest.raises(RecreatePlanStaleError, match="RECREATE_OPERATOR_MISMATCH"):
        manager.apply_recreate(
            plan,
            challenge=plan.challenge,
            operator_id="different-operator",
        )

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("COMMENT ON SCHEMA mra IS 'catalog drift after plan'")

    with pytest.raises(RecreatePlanStaleError, match="RECREATE_PLAN_STALE"):
        manager.apply_recreate(
            plan,
            challenge=plan.challenge,
            operator_id=authorization.operator_id,
        )

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute(
            "COMMENT ON SCHEMA mra IS "
            "'Market Regime Alpha MRA_REFOUNDATION_1 unreleased draft authority schema'"
        )
    replacement_plan = manager.plan_recreate(authorization)
    after = manager.apply_recreate(
        replacement_plan,
        challenge=replacement_plan.challenge,
        operator_id=authorization.operator_id,
    )

    assert after.removed_application_schema == "mra"
    assert after.removed_epoch == SCHEMA_EPOCH
    assert after.removed_catalog_objects == replacement_plan.catalog_objects
    assert after.verification.created is True
    assert after.verification.epoch == SCHEMA_EPOCH
    assert after.verification.catalog_checksum == before.catalog_checksum


def test_recreate_refuses_a_self_inconsistent_catalog(target_database_url: str) -> None:
    manager = SchemaManager(target_database_url)
    manager.bootstrap()
    identity = manager.database_identity()
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("CREATE TABLE mra.unexpected_probe (id bigint PRIMARY KEY)")

    with pytest.raises(CatalogDriftError, match="CATALOG_DRIFT"):
        manager.plan_recreate(
            RecreateAuthorization(
                expected_database_name=identity.database_name,
                expected_database_oid=identity.database_oid,
                operator_id="foundation-test",
                reason="must not approve an internally drifting catalog",
                backup_attestation="isolated disposable test database",
            )
        )


def test_recreate_refuses_a_released_or_wrong_target_epoch(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    manager.bootstrap()
    identity = manager.database_identity()
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute("UPDATE mra.schema_epoch SET release_state = 'RELEASED'")
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")

    with pytest.raises(UnsafeRecreateError, match="unreleased target draft epoch"):
        manager.plan_recreate(
            RecreateAuthorization(
                expected_database_name=identity.database_name,
                expected_database_oid=identity.database_oid,
                operator_id="foundation-test",
                reason="released baselines are immutable",
                backup_attestation="isolated disposable test database",
            )
        )


def test_concurrent_bootstrap_serializes_and_creates_exactly_once(
    target_database_url: str,
) -> None:
    def bootstrap_once(_: int):
        return SchemaManager(target_database_url).bootstrap()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(bootstrap_once, (1, 2)))

    assert sorted(result.created for result in results) == [False, True]
    assert {result.catalog_checksum for result in results} == {
        results[0].catalog_checksum
    }


def test_interrupted_bootstrap_rolls_back_the_entire_schema(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    manager._seed_sql = (  # type: ignore[attr-defined]
        "INSERT INTO mra.does_not_exist VALUES (%s, %s, %s, %s, %s)"
    )

    with pytest.raises(psycopg.errors.UndefinedTable):
        manager.bootstrap()

    with psycopg.connect(target_database_url) as connection:
        assert connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mra')"
        ).fetchone() == (False,)


def test_wrong_epoch_and_seed_checksum_fail_without_repair(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA mra")
        connection.execute(
            """
            CREATE TABLE mra.schema_epoch (
                epoch_name text,
                release_state text,
                baseline_checksum text,
                seed_checksum text,
                catalog_checksum text
            )
            """
        )
        connection.execute(
            "INSERT INTO mra.schema_epoch VALUES (%s, 'DRAFT', %s, %s, %s)",
            ("WRONG_EPOCH", "0" * 64, "0" * 64, "0" * 64),
        )
    with pytest.raises(SchemaEpochMismatchError, match="SCHEMA_EPOCH_MISMATCH"):
        manager.verify()

    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("DROP SCHEMA mra CASCADE")
    manager.bootstrap()
    with psycopg.connect(target_database_url, autocommit=True) as connection:
        connection.execute("ALTER TABLE mra.schema_epoch DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE mra.schema_epoch SET seed_checksum = %s",
            ("0" * 64,),
        )
        connection.execute("ALTER TABLE mra.schema_epoch ENABLE TRIGGER USER")
    with pytest.raises(SchemaChecksumMismatchError, match="SEED_CHECKSUM_MISMATCH"):
        manager.verify()


def test_recreate_requires_zero_other_connections_and_exact_oid(
    target_database_url: str,
) -> None:
    manager = SchemaManager(target_database_url)
    manager.bootstrap()
    identity = manager.database_identity()
    with pytest.raises(UnsafeRecreateError, match="database OID"):
        manager.plan_recreate(
            RecreateAuthorization(
                expected_database_name=identity.database_name,
                expected_database_oid=identity.database_oid + 1,
                operator_id="foundation-test",
                reason="reject the wrong database identity",
                backup_attestation="isolated disposable test database",
            )
        )

    with psycopg.connect(target_database_url):
        with pytest.raises(UnsafeRecreateError, match="zero other client connections"):
            manager.plan_recreate(
                RecreateAuthorization(
                    expected_database_name=identity.database_name,
                    expected_database_oid=identity.database_oid,
                    operator_id="foundation-test",
                    reason="reject active connections",
                    backup_attestation="isolated disposable test database",
                )
            )
