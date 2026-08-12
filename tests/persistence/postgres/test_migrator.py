from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
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
from market_regime_alpha.application.state_system.bundles import (
    state_research_pipeline_identity,
)
from market_regime_alpha.application.state_system.runtime import StateResearchStage
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioPolicy,
    build_shadow_portfolio,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
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


FREE_RUNTIME_MIGRATIONS = (
    (30, "research_summary_v2"),
    (31, "state_system_owned_stages"),
    (32, "research_summary_owner_lineage"),
    (33, "free_runtime_v2_authority_hardening"),
    (34, "shadow_research_authority"),
    (35, "prospective_outcome_authority"),
    (36, "research_evaluation_dataset"),
    (37, "etf_theme_reference_authority"),
    (38, "cross_session_state_authority"),
    (39, "outcome_target_protocol"),
    (40, "prospective_evidence_attestation"),
    (41, "research_evaluation_panel_v2"),
    (42, "shadow_decision_state_policy"),
    (43, "research_validation_engineering"),
    (44, "strategy_shadow_validation"),
    (45, "runtime_authority_evidence"),
    (46, "close_reference_only_qualification"),
    (47, "free_historical_evidence_registry"),
    (48, "free_data_research_universe"),
    (49, "strategy_shadow_portfolio"),
    (50, "security_governance"),
    (51, "path_calibration_hypothesis"),
    (52, "phase_c_protocol_provider_qualification"),
    (53, "research_qualification_authority"),
    (54, "calibration_qualification_authority"),
    (55, "phase_c_gate_authority"),
    (56, "phase_c_correctness_closure"),
    (57, "formal_research_runtime_closure"),
    (58, "locked_oos_roster_authority"),
    (59, "pit_universe_oos_scope_authority"),
    (60, "research_validity_semantics"),
    (61, "research_model_execution"),
    (62, "runtime_scope_historical"),
    (63, "shadow_observation_authority"),
    (64, "shadow_performance_authority"),
    (65, "authoritative_artifact_locator"),
    (66, "formal_execution_assessment"),
    (67, "phase_d_correctness_lineage"),
    (68, "phase_e_historical_corpus"),
)


def test_packaged_migrations_are_contiguous_and_checksummed() -> None:
    migrations = load_packaged_migrations()

    assert tuple(item.version for item in migrations) == tuple(range(1, 69))
    assert len({item.name for item in migrations}) == 68
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

    assert tuple(item.version for item in first) == tuple(range(1, 69))
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) == 68


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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS


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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS


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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS


def test_migrations_024_through_028_upgrade_existing_023_authority(
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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS
    with postgres_factory.connection(read_only=True) as connection:
        latest = connection.execute("SELECT version, name FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
        decision_table = connection.execute("SELECT to_regclass('daily_decision_summary')").fetchone()
    assert latest == FREE_RUNTIME_MIGRATIONS[-1]
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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS
    assert applied == (67,)
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
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS
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
    legacy_stages = (
        *pipeline_result.stages,
        replace(
            pipeline_result.stages[-1],
            stage=StateResearchStage.SIGNAL,
            artifact_id=ArtifactId("legacy-state-signal"),
            artifact_hash=canonical_hash({"legacy": "signal"}),
        ),
        replace(
            pipeline_result.stages[-1],
            stage=StateResearchStage.FORECAST,
            artifact_id=ArtifactId("legacy-state-forecast"),
            artifact_hash=canonical_hash({"legacy": "forecast"}),
        ),
    )
    pipeline_id, pipeline_hash = state_research_pipeline_identity(
        run_id=request.run_id,
        tick_id=request.tick_id,
        as_of_time=request.as_of_time,
        stages=tuple(
            (item.stage.value, item.artifact_id, item.artifact_hash, item.available_at)
            for item in legacy_stages
        ),
    )
    receipt_payload = {
        "schema": "state_system_runtime_receipt/v1",
        "request_idempotency_key": request.idempotency_key,
        "pipeline_artifact_id": str(pipeline_id),
        "pipeline_artifact_hash": pipeline_hash,
        "stage_references": [
            item.to_reference().to_canonical_dict()
            for item in legacy_stages
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
        child_artifact_id=pipeline_id,
        child_artifact_hash=pipeline_hash,
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
        for stage in legacy_stages:
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


def test_migration_028_adds_formal_pit_authority_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:27]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (28, "formal_pit_authority"),
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS
    with postgres_factory.connection(read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = current_schema() AND tablename LIKE 'pit_%'"
            ).fetchall()
        }
        evidence_table = connection.execute(
            "SELECT to_regclass('formal_pit_validation_evidence')"
        ).fetchone()
        guards = {
            row[0]
            for row in connection.execute(
                "SELECT trigger_name FROM information_schema.triggers "
                "WHERE trigger_schema = current_schema() "
                "AND event_object_table = 'pit_source_qualification'"
            ).fetchall()
        }
    assert tables == {
        "pit_artifact_authority_resolution",
        "pit_authority_action",
        "pit_source_qualification",
        "pit_source_qualification_evidence",
        "pit_fact_revision",
        "pit_fact_temporal_authority_resolution",
        "pit_as_of_snapshot",
        "pit_trading_calendar_canonical_snapshot",
        "pit_universe_membership_projection",
        "pit_universe_membership_projection_member",
    }
    assert evidence_table == ("formal_pit_validation_evidence",)
    assert guards == {
        "pit_source_qualification_no_update",
        "pit_source_qualification_no_delete",
    }


def test_migration_029_adds_append_only_research_summary_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:28]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (29, "research_runtime_summary"),
    ) + FREE_RUNTIME_MIGRATIONS
    with postgres_factory.connection(read_only=True) as connection:
        tables = tuple(
            str(value)
            for value in connection.execute(
                "SELECT to_regclass('research_daily_summary'), "
                "to_regclass('research_summary_stage')"
            ).fetchone()
        )
        guards = {
            row[0]
            for row in connection.execute(
                "SELECT trigger_name FROM information_schema.triggers "
                "WHERE trigger_schema = current_schema() "
                "AND event_object_table IN "
                "('research_daily_summary', 'research_summary_stage')"
            ).fetchall()
        }
    assert tables == ("research_daily_summary", "research_summary_stage")
    assert guards == {
        "research_daily_summary_no_delete",
        "research_daily_summary_no_update",
        "research_summary_stage_no_delete",
        "research_summary_stage_no_update",
    }


def test_migration_057_upgrades_056_without_mutating_prior_authorities(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:56]).apply_all(postgres_factory)
    target_hash = canonical_hash({"target": "legacy-056"})
    dataset_hash = canonical_hash({"dataset": "legacy-056"})
    owner_payload = {
        "schema_version": "historical-sample-dataset/v1",
        "target_reference": {
            "artifact_kind": "OUTCOME_TARGET",
            "artifact_id": "legacy-056-target",
            "content_hash": target_hash,
        },
    }
    owner_payload_hash = canonical_hash(owner_payload)
    protocol_hash = canonical_hash({"protocol": "legacy-056"})
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO outcome_target_protocol(
                protocol_id, protocol_hash, protocol_version,
                protocol_json, created_at
            ) VALUES (%s, %s, 'legacy-056', %s, %s)
            """,
            (
                "legacy-056-target-protocol",
                canonical_hash({"target_protocol": "legacy-056"}),
                Jsonb({"schema_version": "outcome-target-protocol/v1"}),
                NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol(
                protocol_id, protocol_hash, protocol_version,
                outcome_target_protocol_id, evaluation_protocol_id,
                trading_calendar_id, trading_calendar_hash,
                payload_json, locked_at, created_at
            ) VALUES (%s, %s, 'legacy-056', %s, 'legacy-evaluation',
                      'legacy-calendar', %s, %s, %s, %s)
            """,
            (
                "legacy-056-formal-protocol",
                protocol_hash,
                "legacy-056-target-protocol",
                canonical_hash({"calendar": "legacy-056"}),
                Jsonb({"schema_version": "formal-research-protocol/v1"}),
                NOW,
                NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol_component_owner_resolution(
                protocol_id, component_role, artifact_kind,
                artifact_id, artifact_hash, owner_kind,
                owner_artifact_id, owner_artifact_hash,
                owner_payload_hash, owner_payload_json,
                owner_recorded_at, resolved_at
            ) VALUES (
                'legacy-056-formal-protocol',
                'historical_sample_dataset_reference',
                'HISTORICAL_SAMPLE_DATASET', 'legacy-056-dataset', %s,
                'RESEARCH_VALIDATION_AUTHORITY', 'legacy-056-dataset', %s,
                %s, %s, %s, %s
            )
            """,
            (
                dataset_hash,
                dataset_hash,
                owner_payload_hash,
                Jsonb(owner_payload),
                NOW,
                NOW,
            ),
        )

    upgraded = PostgresMigrator(migrations=migrations[:57]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in upgraded) == (
        (57, "formal_research_runtime_closure"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        tables = tuple(
            str(value)
            for value in connection.execute(
                """
                SELECT to_regclass('frozen_hypothesis_family'),
                       to_regclass('formal_forecast_computation_receipt'),
                       to_regclass('locked_oos_raw_evidence_unlock'),
                       to_regclass('locked_oos_target_observation_consumption'),
                       to_regclass('formal_hypothesis_family_evaluation')
                """
            ).fetchone()
        )
        old_migration = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = 46"
        ).fetchone()
        old_consumption = connection.execute(
            "SELECT to_regclass('locked_oos_evidence_consumption')"
        ).fetchone()
        legacy_historical = connection.execute(
            """
            SELECT target_id, target_hash, dataset_id, dataset_hash,
                   owner_payload_hash
            FROM formal_research_protocol_historical_dataset
            WHERE formal_protocol_id = 'legacy-056-formal-protocol'
            """
        ).fetchone()
    assert tables == (
        "frozen_hypothesis_family",
        "formal_forecast_computation_receipt",
        "locked_oos_raw_evidence_unlock",
        "locked_oos_target_observation_consumption",
        "formal_hypothesis_family_evaluation",
    )
    assert old_migration is not None
    assert old_consumption == ("locked_oos_evidence_consumption",)
    assert legacy_historical == (
        "legacy-056-target",
        target_hash,
        "legacy-056-dataset",
        dataset_hash,
        owner_payload_hash,
    )


def test_migration_060_preserves_v1_protocols_and_accepts_explicit_inference(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:57]).apply_all(postgres_factory)
    before = canonical_hash({"protocol": "immutable-v1"})
    target_hash = canonical_hash({"target": "immutable-v1"})
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO outcome_target_protocol(
                protocol_id, protocol_hash, protocol_version,
                protocol_json, created_at
            ) VALUES ('immutable-v1-targets', %s, 'v1', %s, %s)
            """,
            (target_hash, Jsonb({"schema_version": "outcome-target-protocol/v1"}), NOW),
        )
        connection.execute(
            """
            INSERT INTO formal_research_protocol(
                protocol_id, protocol_hash, protocol_version,
                outcome_target_protocol_id, evaluation_protocol_id,
                trading_calendar_id, trading_calendar_hash,
                payload_json, locked_at, created_at
            ) VALUES ('immutable-v1-protocol', %s, 'v1',
                      'immutable-v1-targets', 'evaluation-v1', 'calendar-v1',
                      %s, %s, %s, %s)
            """,
            (
                before,
                canonical_hash({"calendar": "immutable-v1"}),
                Jsonb({"schema_version": "formal-research-protocol/v1"}),
                NOW,
                NOW,
            ),
        )

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (58, "locked_oos_roster_authority"),
        (59, "pit_universe_oos_scope_authority"),
        (60, "research_validity_semantics"),
        (61, "research_model_execution"),
        (62, "runtime_scope_historical"),
        (63, "shadow_observation_authority"),
        (64, "shadow_performance_authority"),
        (65, "authoritative_artifact_locator"),
        (66, "formal_execution_assessment"),
        (67, "phase_d_correctness_lineage"),
        (68, "phase_e_historical_corpus"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        stored = connection.execute(
            "SELECT protocol_hash, payload_json FROM formal_research_protocol "
            "WHERE protocol_id = 'immutable-v1-protocol'"
        ).fetchone()
        constraints = " ".join(
            str(row[0])
            for row in connection.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid IN (
                    'formal_research_protocol'::regclass,
                    'frozen_hypothesis_family'::regclass
                )
                ORDER BY conname
                """
            ).fetchall()
        )
    assert stored == (before, {"schema_version": "formal-research-protocol/v1"})
    assert "formal-research-protocol/v2" in constraints
    assert "research-experiment-definition/v1" in constraints
    assert "HOLM_BONFERRONI" in constraints


def test_migration_058_adds_label_blind_locked_oos_roster_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:57]).apply_all(postgres_factory)

    upgraded = PostgresMigrator(migrations=migrations[:58]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in upgraded) == (
        (58, "locked_oos_roster_authority"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        tables = tuple(
            str(value)
            for value in connection.execute(
                """
                SELECT to_regclass('formal_locked_oos_roster'),
                       to_regclass('formal_locked_oos_roster_member')
                """
            ).fetchone()
        )
        guards = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND event_object_table IN (
                    'formal_locked_oos_roster',
                    'formal_locked_oos_roster_member'
                  )
                """
            ).fetchall()
        }
        member_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'formal_locked_oos_roster_member'
                """
            ).fetchall()
        }
    assert tables == (
        "formal_locked_oos_roster",
        "formal_locked_oos_roster_member",
    )
    assert guards == {
        ("formal_locked_oos_roster", "formal_locked_oos_roster_no_update"),
        (
            "formal_locked_oos_roster_member",
            "formal_locked_oos_roster_member_no_update",
        ),
    }
    assert {
        "target_protocol_id",
        "target_protocol_hash",
        "formal_pit_evidence_id",
        "forecast_id",
        "label_id",
        "observation_set_id",
    }.issubset(member_columns)


def test_migration_059_adds_strict_universe_oos_scope_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:58]).apply_all(postgres_factory)

    upgraded = PostgresMigrator(migrations=migrations[:59]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in upgraded) == (
        (59, "pit_universe_oos_scope_authority"),
    )
    expected_tables = {
        "pit_universe_membership_projection",
        "pit_universe_membership_projection_member",
        "formal_locked_oos_roster_universe_binding",
    }
    with postgres_factory.connection(read_only=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = ANY(%s)
                """,
                (list(expected_tables),),
            ).fetchall()
        }
        guards = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT event_object_table, trigger_name
                FROM information_schema.triggers
                WHERE trigger_schema = current_schema()
                  AND event_object_table = ANY(%s)
                """,
                (list(expected_tables),),
            ).fetchall()
        }
    assert tables == expected_tables
    assert guards == {
        (
            "pit_universe_membership_projection",
            "pit_universe_membership_projection_no_update",
        ),
        (
            "pit_universe_membership_projection_member",
            "pit_universe_membership_projection_member_no_update",
        ),
        (
            "formal_locked_oos_roster_universe_binding",
            "formal_locked_oos_roster_universe_binding_no_update",
        ),
    }


def test_migration_067_adds_forward_exact_lineage_without_rewriting_history(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:66]).apply_all(postgres_factory)
    provenance = ShadowParameterProvenance.ENGINEERING_ASSUMPTION
    legacy_policy = ShadowPortfolioPolicy.create(
        policy_version="migration-067-legacy-v1",
        top_k=1,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            name: (value, provenance)
            for name, value in (
                ("commission_bps", Decimal("2")),
                ("slippage_bps", Decimal("5")),
                ("impact_bps", Decimal("3")),
                ("exit_cost_bps", Decimal("2")),
                ("max_participation_rate", Decimal("0.1")),
            )
        },
        created_at=NOW,
    )
    legacy_portfolio = build_shadow_portfolio(
        policy=legacy_policy,
        research_reference=ValidationArtifactReference(
            "RESEARCH_PANEL_V2", ArtifactId("migration-067-legacy-panel"),
            canonical_hash({"legacy": "panel"}),
        ),
        candidate_reference=ValidationArtifactReference(
            "CANDIDATE_SET", ArtifactId("migration-067-legacy-candidates"),
            canonical_hash({"legacy": "candidates"}),
        ),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO strategy_shadow_portfolio(
                portfolio_id, portfolio_hash, policy_id, policy_hash,
                research_artifact_id, candidate_artifact_id, initial_cash,
                policy_json, portfolio_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(legacy_portfolio.portfolio_id),
                legacy_portfolio.portfolio_hash,
                str(legacy_policy.policy_id),
                legacy_policy.policy_hash,
                str(legacy_portfolio.research_reference.artifact_id),
                str(legacy_portfolio.candidate_reference.artifact_id),
                legacy_portfolio.initial_cash,
                Jsonb(legacy_policy.to_canonical_dict()),
                Jsonb(legacy_portfolio.to_canonical_dict()),
                legacy_portfolio.created_at,
            ),
        )

    upgraded = PostgresMigrator(migrations=migrations[:67]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in upgraded) == (
        (67, "phase_d_correctness_lineage"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        tables = tuple(
            str(item)
            for item in connection.execute(
                """
                SELECT to_regclass('strategy_shadow_session_lineage_binding'),
                       to_regclass(
                         'strategy_shadow_portfolio_state_source_binding'
                       )
                """
            ).fetchone()
        )
        columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'strategy_shadow_portfolio'
                """
            ).fetchall()
        }
        session_columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'strategy_shadow_session'
                """
            ).fetchall()
        }
        policy_unique = connection.execute(
            """
            SELECT count(*) FROM pg_constraint
            WHERE conrelid = 'strategy_shadow_portfolio'::regclass
              AND conname = 'strategy_shadow_portfolio_policy_id_key'
            """
        ).fetchone()
        legacy_projection = connection.execute(
            """
            SELECT lineage_status, research_artifact_hash,
                   candidate_artifact_hash, strategy_session_id,
                   strategy_session_hash
            FROM strategy_shadow_portfolio WHERE portfolio_id = %s
            """,
            (str(legacy_portfolio.portfolio_id),),
        ).fetchone()
    assert tables == (
        "strategy_shadow_session_lineage_binding",
        "strategy_shadow_portfolio_state_source_binding",
    )
    assert {
        "research_artifact_hash",
        "candidate_artifact_hash",
        "strategy_session_id",
        "strategy_session_hash",
        "lineage_status",
    }.issubset(columns)
    assert "lineage_status" in session_columns
    assert policy_unique is not None and int(policy_unique[0]) == 0
    assert legacy_projection == ("LEGACY_UNBOUND", None, None, None, None)
    assert PostgresShadowPortfolioRepository(
        postgres_factory,
        apply_migrations=False,
    ).get_portfolio(legacy_portfolio.portfolio_id) == (
        legacy_policy,
        legacy_portfolio,
    )
