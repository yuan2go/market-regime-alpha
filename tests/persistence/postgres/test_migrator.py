from __future__ import annotations

from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json

import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionResult,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import (
    PostgresMigration,
    PostgresMigrationChecksumError,
    PostgresMigrationSequenceError,
    PostgresMigrator,
    load_packaged_migrations,
)
from market_regime_alpha.platform.contracts import EvidenceLevel, ModelLifecycleStatus
from market_regime_alpha.platform.governance_serialization import (
    model_registration_to_dict,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from tests.platform.test_platform_kernel import _model_definition
from tests.application.decision_system.support import observation
from tests.application.state_system.test_repositories import _active_claim
from tests.application.state_system.test_runtime import (
    _pipeline as _state_pipeline,
    _request as _state_request,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    NOW,
    MutableClock,
)


def test_packaged_migrations_are_contiguous_and_checksummed() -> None:
    migrations = load_packaged_migrations()

    assert tuple(item.version for item in migrations) == tuple(range(1, 28))
    assert len({item.name for item in migrations}) == 27
    assert all(item.checksum == sha256(item.sql.encode("utf-8")).hexdigest() for item in migrations)


def test_missing_migration_version_is_rejected() -> None:
    migrations = (
        PostgresMigration.create(1, "one", "SELECT 1;"),
        PostgresMigration.create(3, "three", "SELECT 3;"),
    )

    with pytest.raises(PostgresMigrationSequenceError, match="contiguous"):
        PostgresMigrator(migrations=migrations)


def test_apply_all_is_idempotent(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrator = PostgresMigrator()

    first = migrator.apply_all(postgres_factory)
    second = migrator.apply_all(postgres_factory)

    assert tuple(item.version for item in first) == tuple(range(1, 28))
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) == 27


def test_applied_checksum_drift_is_rejected(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (PostgresMigration.create(1, "one", "SELECT 1;"),)
    PostgresMigrator(migrations=migrations).apply_all(postgres_factory)
    changed = (PostgresMigration.create(1, "one", "SELECT 2;"),)

    with pytest.raises(PostgresMigrationChecksumError, match="checksum"):
        PostgresMigrator(migrations=changed).apply_all(postgres_factory)


def test_failed_migration_does_not_record_version(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (
        PostgresMigration.create(1, "one", "CREATE TABLE durable_one(id bigint PRIMARY KEY);"),
        PostgresMigration.create(2, "broken", "CREATE TABL invalid syntax;"),
    )

    with pytest.raises(Exception):
        PostgresMigrator(migrations=migrations).apply_all(postgres_factory)
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        durable = connection.execute("SELECT to_regclass('durable_one')").fetchone()
    assert rows == [(1,)]
    assert durable == ("durable_one",)


def test_concurrent_migrators_are_serialized(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = (
        PostgresMigration.create(
            1,
            "serialized",
            "SELECT pg_sleep(0.05); CREATE TABLE serialized_once(id bigint PRIMARY KEY);",
        ),
    )
    migrator = PostgresMigrator(migrations=migrations)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: migrator.apply_all(postgres_factory), range(2)))

    assert sorted(len(result) for result in results) == [0, 1]


def test_migration_021_upgrades_an_existing_020_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:20]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (21, "continuous_runtime_schedule"),
        (22, "state_system_dynamic_pool"),
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
        (27, "model_runtime_governance"),
    )


def test_migration_022_upgrades_an_existing_021_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:21]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (22, "state_system_dynamic_pool"),
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
        (27, "model_runtime_governance"),
    )


def test_migration_023_upgrades_an_existing_022_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:22]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (23, "state_system_runtime_child"),
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
        (27, "model_runtime_governance"),
    )


def test_migrations_024_through_027_upgrade_existing_023_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:23]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (24, "postgres_only_authority"),
        (25, "decision_system"),
        (26, "decision_authority_hardening"),
        (27, "model_runtime_governance"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        latest = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        decision_table = connection.execute("SELECT to_regclass('daily_decision_summary')").fetchone()
    assert latest == (27, "model_runtime_governance")
    assert decision_table == ("daily_decision_summary",)


def test_migration_026_preserves_prerelease_v1_decision_rows_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:25]).apply_all(postgres_factory)
    account = observation(positions=())
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO manual_account_observation(
                observation_id, content_hash, account_id, trading_date,
                as_of_time, total_equity, available_cash, frozen_cash,
                source, actor, reason, notes, idempotency_key, command_hash,
                revision, previous_observation_id, payload_json, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                str(account.observation_id),
                account.content_hash,
                account.account_id,
                account.trading_date,
                account.as_of_time,
                account.total_equity,
                account.available_cash,
                account.frozen_cash,
                account.source,
                account.actor,
                account.reason,
                account.notes,
                account.idempotency_key,
                account.content_hash,
                account.revision,
                None,
                Jsonb(account.to_canonical_dict()),
                account.created_at,
            ),
        )

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        applied = connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()
    restored = PostgresDecisionSystemRepository(
        postgres_factory
    ).get_manual_observation(account.observation_id)
    assert tuple((item.version, item.name) for item in upgraded) == (
        (26, "decision_authority_hardening"),
        (27, "model_runtime_governance"),
    )
    assert applied == (27,)
    assert restored == account


def test_migration_027_backfills_existing_registry_history_and_guards_it(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:26]).apply_all(postgres_factory)
    definition = _model_definition()
    registry = ModelRegistry()
    registry.register(definition)
    registration = registry.transition(
        definition.model_id,
        to_status=ModelLifecycleStatus.RESEARCH,
        changed_at=datetime(2026, 8, 8, 6, 0, tzinfo=UTC),
        reason="pre-027 research transition",
        evidence_refs=("pre-027-evidence",),
        evidence_level=EvidenceLevel.EXPLORATORY,
    )
    payload = model_registration_to_dict(registration)
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO model_registrations(
                model_id, registration_json, definition_hash,
                lifecycle_status, evidence_level, version
            ) VALUES (%s, %s, %s, %s, %s, 1)
            """,
            (
                str(definition.model_id),
                json.dumps(payload, sort_keys=True),
                definition.definition_hash,
                registration.lifecycle_status.value,
                registration.evidence_level.value,
            ),
        )
        connection.execute(
            """
            INSERT INTO model_lifecycle_transitions(
                model_id, sequence, transition_json, idempotency_key
            ) VALUES (%s, 1, %s, 'pre-027-transition')
            """,
            (
                str(definition.model_id),
                json.dumps(payload["transitions"][0], sort_keys=True),
            ),
        )
        for key, version, digest in (
            ("pre-027-register", 0, "sha256:" + "1" * 64),
            ("pre-027-transition", 1, "sha256:" + "2" * 64),
            ("pre-027-reregister", 1, "sha256:" + "3" * 64),
        ):
            connection.execute(
                """
                INSERT INTO governance_commands(
                    idempotency_key, aggregate_type, aggregate_id,
                    payload_hash, result_version, created_at
                ) VALUES (%s, 'MODEL', %s, %s, %s, %s)
                """,
                (
                    key,
                    str(definition.model_id),
                    digest,
                    version,
                    datetime(2026, 8, 8, 6, version, tzinfo=UTC),
                ),
            )

    upgraded = PostgresMigrator().apply_all(postgres_factory)
    with postgres_factory.connection(read_only=True) as connection:
        actions = connection.execute(
            "SELECT action_type, aggregate_id FROM model_governance_action "
            "ORDER BY governance_revision"
        ).fetchall()
        stored_version = connection.execute(
            "SELECT version FROM model_registrations WHERE model_id = %s",
            (str(definition.model_id),),
        ).fetchone()
    assert tuple((item.version, item.name) for item in upgraded) == (
        (27, "model_runtime_governance"),
    )
    assert actions == [
        ("MODEL_REGISTER", str(definition.model_id)),
        ("MODEL_REGISTER", str(definition.model_id)),
        ("MODEL_LIFECYCLE_TRANSITION", str(definition.model_id)),
    ]
    assert stored_version == (1,)
    with postgres_factory.connection() as connection:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE model_governance_action SET reason = 'tamper'"
            )
        connection.rollback()


def test_migration_027_preserves_legacy_state_receipt_as_unqualified(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:26]).apply_all(postgres_factory)
    clock = MutableClock(NOW)
    _, claim = _active_claim(postgres_factory, clock)
    request = _state_request(claim)
    pipeline, _ = _state_pipeline()
    pipeline_result = pipeline.execute(request)
    receipt_payload = {
        "schema": "state_system_runtime_receipt/v1",
        "request_idempotency_key": request.idempotency_key,
        "pipeline_artifact_id": str(pipeline_result.artifact_id),
        "pipeline_artifact_hash": pipeline_result.artifact_hash,
        "stage_references": [
            item.to_reference().to_canonical_dict()
            for item in pipeline_result.stages
        ],
        "reason_codes": list(pipeline_result.reason_codes),
    }
    receipt_hash = canonical_hash(receipt_payload)
    result = ChildExecutionResult(
        child_kind=ContinuousChildKind.STATE_SYSTEM,
        child_run_id=ArtifactId(
            "state-system-run:"
            f"{request.idempotency_key.removeprefix('continuous-children-')}"
        ),
        child_receipt_id=ArtifactId(f"state-system-receipt:{receipt_hash[7:]}"),
        child_receipt_hash=receipt_hash,
        child_artifact_id=pipeline_result.artifact_id,
        child_artifact_hash=pipeline_result.artifact_hash,
        input_references=request.input_references,
        configuration_references=request.configuration_references,
    )
    stored_receipt = {
        "schema": "state_runtime_child_receipt/v2",
        "child_kind": result.child_kind.value,
        "child_run_id": str(result.child_run_id),
        "child_receipt_id": str(result.child_receipt_id),
        "child_receipt_hash": result.child_receipt_hash,
        "child_artifact_id": str(result.child_artifact_id),
        "child_artifact_hash": result.child_artifact_hash,
        "input_references": [
            item.to_canonical_dict() for item in result.input_references
        ],
        "configuration_references": [
            item.to_canonical_dict()
            for item in result.configuration_references
        ],
        "receipt_payload": receipt_payload,
    }
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO state_runtime_receipt(
                receipt_id, receipt_hash, run_id, tick_id, pool_id,
                status, receipt_json, created_at
            ) VALUES (%s, %s, %s, %s, NULL, 'COMPLETED', %s, %s)
            """,
            (
                str(result.child_receipt_id),
                result.child_receipt_hash,
                str(request.run_id),
                str(request.tick_id),
                json.dumps(stored_receipt, sort_keys=True),
                NOW,
            ),
        )
        for stage in pipeline_result.stages:
            connection.execute(
                """
                INSERT INTO state_research_stage_authority(
                    run_id, tick_id, state_receipt_id, stage,
                    artifact_id, artifact_hash, available_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(request.run_id),
                    str(request.tick_id),
                    str(result.child_receipt_id),
                    stage.stage.value,
                    str(stage.artifact_id),
                    stage.artifact_hash,
                    stage.available_at,
                    NOW,
                ),
            )

    PostgresMigrator().apply_all(postgres_factory)

    restored = PostgresStateSystemRepository(
        postgres_factory, clock=clock
    ).lookup_runtime_child(request)
    with postgres_factory.connection(read_only=True) as connection:
        eligibilities = connection.execute(
            "SELECT DISTINCT data_eligibility "
            "FROM state_research_stage_authority"
        ).fetchall()
    assert restored == result
    assert eligibilities == [(None,)]
