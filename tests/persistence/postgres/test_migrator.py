from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
import json

import pytest
from psycopg.types.json import Jsonb

from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
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
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
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
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.platform.contracts import EvidenceLevel, ModelLifecycleStatus
from market_regime_alpha.platform.governance_serialization import (
    model_registration_to_dict,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from tests.platform.test_platform_kernel import _model_definition
from tests.application.decision_system.support import observation
from tests.application.state_system.test_runtime import (
    _pipeline as _state_pipeline,
    _request as _state_request,
)
from tests.persistence.postgres.test_continuous_research_journal import (
    NOW,
    MutableClock,
    _command,
    _tick,
)
from tests.application.historical_research.test_contracts import (
    _command as _historical_command,
)
from tests.universe.test_historical_security_facts import _owner
from tests.universe.test_runtime_scope import _policy


pytestmark = pytest.mark.unmigrated_postgres


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
    (69, "phase_e2_selective_historical_reads"),
    (70, "historical_constituent_universe"),
    (71, "longitudinal_historical_security_facts"),
    (72, "historical_component_keyset_streaming"),
    (73, "historical_constituent_timeline"),
    (74, "historical_outcome_label_projection"),
    (75, "phase_e3_lineage_and_fact_gap_closure"),
    (76, "historical_fact_acquisition_scope"),
    (77, "historical_context_instrument_set"),
    (78, "historical_outcome_temporal_projection"),
    (79, "historical_fact_identity_projection"),
    (80, "historical_experiment_definition"),
    (81, "historical_runtime_contract"),
    (82, "historical_fact_projection_membership"),
    (83, "longitudinal_owner_identity_closure"),
    (84, "historical_feature_configuration_owner"),
    (85, "multi_strategy_business_closure"),
    (86, "stateful_strategy_lifecycle"),
    (87, "strategy_execution_integrity"),
    (88, "portfolio_execution_authority"),
    (89, "golden_loop_v2_evidence"),
    (90, "tie_aware_pool_ranks"),
    (91, "alpha_research_phase_ii"),
    (92, "strategy_forecast_contract_semantics"),
    (93, "frozen_temporal_validation_window"),
    (94, "pre_strategy_risk_opportunity"),
    (95, "daily_alpha_continuous_projection"),
    (96, "daily_alpha_outcome_lineage"),
    (97, "daily_alpha_target_session"),
    (98, "wp_alpha_proof_locked_scope"),
    (99, "historical_fact_membership_index"),
    (100, "historical_fact_guard_fk_indexes"),
    (101, "locked_oos_typed_calendar_owner"),
    (102, "historical_component_physical_payload"),
    (103, "historical_outcome_forecast_index"),
    (104, "historical_outcome_forecast_fk_index"),
    (105, "alpha_correctness_target_semantics"),
)


def test_packaged_migrations_are_contiguous_and_checksummed() -> None:
    migrations = load_packaged_migrations()

    assert tuple(item.version for item in migrations) == tuple(range(1, 106))
    assert len({item.name for item in migrations}) == 105
    assert all(item.checksum == sha256(item.sql.encode("utf-8")).hexdigest() for item in migrations)


def test_migration_089_admits_v2_evidence_without_mutating_v1_rows(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:88]).apply_all(postgres_factory)
    with postgres_factory.connection(read_only=True) as connection:
        before = connection.execute(
            "SELECT count(*) FROM historical_research_evidence"
        ).fetchone()

    applied = PostgresMigrator(migrations=migrations[:89]).apply_all(
        postgres_factory
    )

    with postgres_factory.connection(read_only=True) as connection:
        after = connection.execute(
            "SELECT count(*) FROM historical_research_evidence"
        ).fetchone()
        constraints = " ".join(
            str(row[0])
            for row in connection.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname IN (
                    'historical_corpus_session_component_component_kind_check',
                    'historical_research_evidence_evidence_kind_check'
                )
                ORDER BY conname
                """
            ).fetchall()
        )
    assert tuple((item.version, item.name) for item in applied) == (
        (89, "golden_loop_v2_evidence"),
    )
    assert after == before
    assert "RESEARCH_EVALUATION" in constraints
    assert "METHODOLOGY_ASSESSMENT" in constraints


def test_migration_090_removes_rank_as_dynamic_pool_member_identity(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:89]).apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        before = connection.execute(
            """
            SELECT count(*)
            FROM pg_constraint
            WHERE conrelid = 'dynamic_stock_pool_member'::regclass
              AND conname = 'dynamic_stock_pool_member_pool_id_rank_key'
            """
        ).fetchone()

    applied = PostgresMigrator(migrations=migrations[:90]).apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        after = connection.execute(
            """
            SELECT count(*)
            FROM pg_constraint
            WHERE conrelid = 'dynamic_stock_pool_member'::regclass
              AND conname = 'dynamic_stock_pool_member_pool_id_rank_key'
            """
        ).fetchone()
        primary_key = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'dynamic_stock_pool_member'::regclass
              AND contype = 'p'
            """
        ).fetchone()

    assert before == (1,)
    assert tuple((item.version, item.name) for item in applied) == (
        (90, "tie_aware_pool_ranks"),
    )
    assert after == (0,)
    assert primary_key == ("PRIMARY KEY (pool_id, symbol)",)


def test_migration_075_enforces_exact_owner_hash_pairs(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        definitions = {
            str(row[0]): tuple(str(item) for item in row[1])
            for row in connection.execute(
                """
                SELECT conrelid::regclass::text,
                       array_agg(pg_get_constraintdef(oid) ORDER BY conname)
                FROM pg_constraint
                WHERE conrelid IN (
                    'free_data_historical_constituent_timeline_cohort'::regclass,
                    'historical_corpus_outcome_label'::regclass
                )
                  AND contype = 'f'
                GROUP BY conrelid
                ORDER BY conrelid::regclass::text
                """
            ).fetchall()
        }

    assert any(
        "FOREIGN KEY (snapshot_id, snapshot_hash)" in item for item in definitions["free_data_historical_constituent_timeline_cohort"]
    )
    assert any("FOREIGN KEY (component_id, component_hash)" in item for item in definitions["historical_corpus_outcome_label"])


def test_migration_076_projects_historical_fact_acquisition_scope(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        columns = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'free_data_historical_security_fact_set'
                """
            ).fetchall()
        }

    assert {
        "acquisition_start_date",
        "acquisition_end_date",
        "requested_symbols",
        "universe_scope_references",
    }.issubset(columns)


def test_migration_078_binds_outcome_projection_to_owner_session_date(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    PostgresMigrator().apply_all(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'historical_corpus_outcome_label'::regclass
              AND conname = 'historical_corpus_outcome_label_temporal_owner_fk'
            """
        ).fetchone()

    assert definition is not None
    assert "FOREIGN KEY (component_id, component_hash, trading_date)" in str(definition[0])


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

    assert tuple(item.version for item in first) == tuple(range(1, 106))
    assert second == ()
    with postgres_factory.connection(read_only=True) as connection:
        rows = connection.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) == 105


def test_verify_current_is_read_only_and_requires_complete_head(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:-1]).apply_all(postgres_factory)

    with pytest.raises(PostgresMigrationSequenceError, match="missing versions: \\[105\\]"):
        PostgresMigrator().verify_current(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        stored = connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()
    assert stored == (104,)


def test_verify_current_rejects_missing_registry_without_creating_it(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    with pytest.raises(PostgresMigrationSequenceError, match="registry is missing"):
        PostgresMigrator().verify_current(postgres_factory)

    with postgres_factory.connection(read_only=True) as connection:
        registry = connection.execute(
            "SELECT to_regclass('schema_migrations')"
        ).fetchone()
    assert registry == (None,)


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

    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (21, "continuous_runtime_schedule"),
            (22, "state_system_dynamic_pool"),
            (23, "state_system_runtime_child"),
            (24, "postgres_only_authority"),
            (25, "decision_system"),
            (26, "decision_authority_hardening"),
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )


def test_migration_022_upgrades_an_existing_021_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:21]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (22, "state_system_dynamic_pool"),
            (23, "state_system_runtime_child"),
            (24, "postgres_only_authority"),
            (25, "decision_system"),
            (26, "decision_authority_hardening"),
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )


def test_migration_023_upgrades_an_existing_022_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:22]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (23, "state_system_runtime_child"),
            (24, "postgres_only_authority"),
            (25, "decision_system"),
            (26, "decision_authority_hardening"),
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )


def test_migrations_024_through_028_upgrade_existing_023_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:23]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (24, "postgres_only_authority"),
            (25, "decision_system"),
            (26, "decision_authority_hardening"),
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )
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
        applied = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
    restored = PostgresDecisionSystemRepository(postgres_factory).get_manual_observation(account.observation_id)
    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (26, "decision_authority_hardening"),
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )
    assert applied == (105,)
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
            "SELECT action_type, aggregate_id FROM model_governance_action ORDER BY governance_revision"
        ).fetchall()
        stored_version = connection.execute(
            "SELECT version FROM model_registrations WHERE model_id = %s",
            (str(definition.model_id),),
        ).fetchone()
    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (27, "model_runtime_governance"),
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )
    assert actions == [
        ("MODEL_REGISTER", str(definition.model_id)),
        ("MODEL_REGISTER", str(definition.model_id)),
        ("MODEL_LIFECYCLE_TRANSITION", str(definition.model_id)),
    ]
    assert stored_version == (1,)
    with postgres_factory.connection() as connection:
        with pytest.raises(Exception, match="append-only"):
            connection.execute("UPDATE model_governance_action SET reason = 'tamper'")
        connection.rollback()


def test_migration_027_preserves_legacy_state_receipt_as_unqualified(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:26]).apply_all(postgres_factory)
    clock = MutableClock(NOW)
    command = _command()
    tick = _tick(command)
    lease_expires_at = NOW.replace(minute=NOW.minute + 10)
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO continuous_research_run(
                run_id, idempotency_key, command_hash, command_json,
                trading_date, request_scope_hash, policy_id, policy_hash,
                provider_configuration_id, provider_configuration_hash,
                research_configuration_id, research_configuration_hash,
                status, current_tick_sequence, version, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'DECISION_WINDOW_OPEN', 1, 2, %s, %s
            )
            """,
            (
                str(command.run_id),
                command.idempotency_key,
                command.command_hash,
                json.dumps(command.to_canonical_dict(), sort_keys=True),
                command.trading_date,
                command.request_scope_hash,
                str(command.policy_id),
                command.policy_hash,
                str(command.provider_configuration_id),
                command.provider_configuration_hash,
                str(command.research_configuration_id),
                command.research_configuration_hash,
                NOW,
                NOW,
            ),
        )
        connection.execute(
            """
            INSERT INTO continuous_runtime_tick(
                run_id, tick_id, idempotency_key, tick_hash, tick_json,
                tick_sequence, observed_at, session_phase, status, version,
                claim_id, fencing_token, lease_acquired_at, lease_expires_at,
                heartbeat_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, 1, %s, 'DECISION_WINDOW',
                'IN_PROGRESS', 2, 'legacy-migration-claim', 1, %s, %s, %s, %s, %s
            )
            """,
            (
                str(command.run_id),
                str(tick.tick_id),
                tick.idempotency_key,
                tick.tick_hash,
                json.dumps(tick.to_canonical_dict(), sort_keys=True),
                tick.observed_at,
                NOW,
                lease_expires_at,
                NOW,
                NOW,
                NOW,
            ),
        )
    claim = ClaimedRuntimeTick(
        run_id=command.run_id,
        tick_id=tick.tick_id,
        tick_sequence=1,
        claim_id="legacy-migration-claim",
        fencing_token=1,
        tick_version=2,
        lease_acquired_at=NOW,
        lease_expires_at=lease_expires_at,
        heartbeat_at=NOW,
    )
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
        stages=tuple((item.stage.value, item.artifact_id, item.artifact_hash, item.available_at) for item in legacy_stages),
    )
    receipt_payload = {
        "schema": "state_system_runtime_receipt/v1",
        "request_idempotency_key": request.idempotency_key,
        "pipeline_artifact_id": str(pipeline_id),
        "pipeline_artifact_hash": pipeline_hash,
        "stage_references": [item.to_reference().to_canonical_dict() for item in legacy_stages],
        "reason_codes": list(pipeline_result.reason_codes),
    }
    receipt_hash = canonical_hash(receipt_payload)
    result = ChildExecutionResult(
        child_kind=ContinuousChildKind.STATE_SYSTEM,
        child_run_id=ArtifactId(f"state-system-run:{request.idempotency_key.removeprefix('continuous-children-')}"),
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
        "input_references": [item.to_canonical_dict() for item in result.input_references],
        "configuration_references": [item.to_canonical_dict() for item in result.configuration_references],
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

    restored = PostgresStateSystemRepository(postgres_factory, clock=clock).lookup_runtime_child(request)
    with postgres_factory.connection(read_only=True) as connection:
        eligibilities = connection.execute("SELECT DISTINCT data_eligibility FROM state_research_stage_authority").fetchall()
    assert restored == result
    assert eligibilities == [(None,)]


def test_migration_028_adds_formal_pit_authority_forward_only(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:27]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert (
        tuple((item.version, item.name) for item in upgraded)
        == (
            (28, "formal_pit_authority"),
            (29, "research_runtime_summary"),
        )
        + FREE_RUNTIME_MIGRATIONS
    )
    with postgres_factory.connection(read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = current_schema() AND tablename LIKE 'pit_%'"
            ).fetchall()
        }
        evidence_table = connection.execute("SELECT to_regclass('formal_pit_validation_evidence')").fetchone()
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

    assert tuple((item.version, item.name) for item in upgraded) == ((29, "research_runtime_summary"),) + FREE_RUNTIME_MIGRATIONS
    with postgres_factory.connection(read_only=True) as connection:
        tables = tuple(
            str(value)
            for value in connection.execute(
                "SELECT to_regclass('research_daily_summary'), to_regclass('research_summary_stage')"
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

    upgraded = PostgresMigrator(migrations=migrations[:57]).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == ((57, "formal_research_runtime_closure"),)
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
        old_migration = connection.execute("SELECT checksum FROM schema_migrations WHERE version = 46").fetchone()
        old_consumption = connection.execute("SELECT to_regclass('locked_oos_evidence_consumption')").fetchone()
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
        (69, "phase_e2_selective_historical_reads"),
        (70, "historical_constituent_universe"),
        (71, "longitudinal_historical_security_facts"),
        (72, "historical_component_keyset_streaming"),
        (73, "historical_constituent_timeline"),
        (74, "historical_outcome_label_projection"),
        (75, "phase_e3_lineage_and_fact_gap_closure"),
        (76, "historical_fact_acquisition_scope"),
        (77, "historical_context_instrument_set"),
        (78, "historical_outcome_temporal_projection"),
        (79, "historical_fact_identity_projection"),
        (80, "historical_experiment_definition"),
        (81, "historical_runtime_contract"),
        (82, "historical_fact_projection_membership"),
        (83, "longitudinal_owner_identity_closure"),
        (84, "historical_feature_configuration_owner"),
        (85, "multi_strategy_business_closure"),
        (86, "stateful_strategy_lifecycle"),
        (87, "strategy_execution_integrity"),
        (88, "portfolio_execution_authority"),
        (89, "golden_loop_v2_evidence"),
        (90, "tie_aware_pool_ranks"),
        (91, "alpha_research_phase_ii"),
        (92, "strategy_forecast_contract_semantics"),
        (93, "frozen_temporal_validation_window"),
        (94, "pre_strategy_risk_opportunity"),
        (95, "daily_alpha_continuous_projection"),
        (96, "daily_alpha_outcome_lineage"),
        (97, "daily_alpha_target_session"),
        (98, "wp_alpha_proof_locked_scope"),
        (99, "historical_fact_membership_index"),
        (100, "historical_fact_guard_fk_indexes"),
        (101, "locked_oos_typed_calendar_owner"),
        (102, "historical_component_physical_payload"),
        (103, "historical_outcome_forecast_index"),
        (104, "historical_outcome_forecast_fk_index"),
        (105, "alpha_correctness_target_semantics"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        stored = connection.execute(
            "SELECT protocol_hash, payload_json FROM formal_research_protocol WHERE protocol_id = 'immutable-v1-protocol'"
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

    upgraded = PostgresMigrator(migrations=migrations[:58]).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == ((58, "locked_oos_roster_authority"),)
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

    upgraded = PostgresMigrator(migrations=migrations[:59]).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == ((59, "pit_universe_oos_scope_authority"),)
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
            "RESEARCH_PANEL_V2",
            ArtifactId("migration-067-legacy-panel"),
            canonical_hash({"legacy": "panel"}),
        ),
        candidate_reference=ValidationArtifactReference(
            "CANDIDATE_SET",
            ArtifactId("migration-067-legacy-candidates"),
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

    upgraded = PostgresMigrator(migrations=migrations[:67]).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == ((67, "phase_d_correctness_lineage"),)
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


def test_migration_099_backfills_indexed_historical_fact_membership_guards(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    migration_099 = tuple(item for item in migrations if item.version <= 99)
    assert (migration_099[-1].version, migration_099[-1].name) == (
        99,
        "historical_fact_membership_index",
    )
    PostgresMigrator(migrations=migrations[:98]).apply_all(postgres_factory)
    repository = PostgresHistoricalSecurityFactsRepository(
        postgres_factory,
        apply_migrations=False,
    )
    owner = repository.publish(_owner(include_gap=True))

    upgraded = PostgresMigrator(migrations=migration_099).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (99, "historical_fact_membership_index"),
    )
    assert repository.publish(owner) == owner
    with postgres_factory.connection(read_only=True) as connection:
        fact_count, gap_count = connection.execute(
            """
            SELECT (
                       SELECT count(*)
                       FROM free_data_historical_security_fact_member_guard
                       WHERE owner_id = %s AND owner_hash = %s
                   ),
                   (
                       SELECT count(*)
                       FROM free_data_historical_security_fact_gap_member_guard
                       WHERE owner_id = %s AND owner_hash = %s
                   )
            """,
            (
                str(owner.owner_id),
                owner.owner_hash,
                str(owner.owner_id),
                owner.owner_hash,
            ),
        ).fetchone()
    assert fact_count == len(owner.facts)
    assert gap_count == len(owner.coverage_gaps)


def test_migrations_098_through_105_upgrade_existing_097_authority(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    PostgresMigrator(migrations=migrations[:97]).apply_all(postgres_factory)

    upgraded = PostgresMigrator().apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (98, "wp_alpha_proof_locked_scope"),
        (99, "historical_fact_membership_index"),
        (100, "historical_fact_guard_fk_indexes"),
        (101, "locked_oos_typed_calendar_owner"),
        (102, "historical_component_physical_payload"),
        (103, "historical_outcome_forecast_index"),
        (104, "historical_outcome_forecast_fk_index"),
        (105, "alpha_correctness_target_semantics"),
    )
    assert len(PostgresMigrator().verify_current(postgres_factory)) == 105


def test_migration_100_indexes_historical_fact_guard_owner_foreign_keys(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    migration_100 = tuple(item for item in migrations if item.version <= 100)
    assert (migration_100[-1].version, migration_100[-1].name) == (
        100,
        "historical_fact_guard_fk_indexes",
    )
    PostgresMigrator(migrations=migrations[:99]).apply_all(postgres_factory)

    upgraded = PostgresMigrator(migrations=migration_100).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (100, "historical_fact_guard_fk_indexes"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        indexes = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT indexname
                FROM pg_catalog.pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname IN (
                    'free_data_historical_security_fact_member_guard_owner_idx',
                    'free_data_historical_security_fact_gap_member_guard_owner_idx'
                  )
                """
            ).fetchall()
        }
    assert indexes == {
        "free_data_historical_security_fact_member_guard_owner_idx",
        "free_data_historical_security_fact_gap_member_guard_owner_idx",
    }


def test_migration_101_binds_locked_scope_to_typed_calendar_owner(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    assert (migrations[100].version, migrations[100].name) == (
        101,
        "locked_oos_typed_calendar_owner",
    )
    PostgresMigrator(migrations=migrations[:100]).apply_all(postgres_factory)

    upgraded = PostgresMigrator(migrations=migrations[:101]).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in upgraded) == (
        (101, "locked_oos_typed_calendar_owner"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_catalog.pg_constraint
            WHERE conrelid = 'frozen_locked_oos_scope'::regclass
              AND conname = 'frozen_locked_oos_scope_calendar_owner_fk'
            """
        ).fetchone()
    assert definition is not None
    assert "pit_trading_calendar_canonical_snapshot" in str(definition[0])


def test_migration_102_adds_external_payload_projection_without_mutating_inline_rows(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    assert (migrations[101].version, migrations[101].name) == (
        102,
        "historical_component_physical_payload",
    )
    PostgresMigrator(migrations=migrations[:101]).apply_all(postgres_factory)

    command = _historical_command(sessions=(date(2020, 1, 2),))
    PostgresRuntimeScopeRepository(postgres_factory).register_policy(_policy())
    PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(NOW),
    ).create_or_get(command)
    request = command.session_request(date(2020, 1, 2))
    source = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("migration-102-source"),
        canonical_hash({"migration": 102}),
    )
    component = HistoricalSessionComponent.create(
        run_id=command.run_id,
        session_id=request.session_id,
        trading_date=request.trading_date,
        component_kind=HistoricalComponentKind.FEATURE,
        source_max_event_time=request.decision_time,
        materialized_at=request.materialized_at,
        source_references=(source,),
        payload={"legacy": "inline"},
    )
    with postgres_factory.connection() as connection:
        connection.execute(
            """
            INSERT INTO historical_corpus_session_component(
                component_id, component_hash, run_id, session_id,
                trading_date, ordinal, component_kind,
                source_max_event_time, materialized_at, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s)
            """,
            (
                str(component.component_id),
                component.component_hash,
                str(component.run_id),
                str(component.session_id),
                component.trading_date,
                component.component_kind.value,
                component.source_max_event_time,
                component.materialized_at,
                Jsonb(component.to_canonical_dict()),
                component.materialized_at,
            ),
        )

    upgraded = PostgresMigrator(migrations=migrations[:102]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in upgraded) == (
        (102, "historical_component_physical_payload"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT payload_storage, payload_locator, payload_json
            FROM historical_corpus_session_component
            WHERE component_id = %s
            """,
            (str(component.component_id),),
        ).fetchone()
    assert row is not None
    assert row[0] == "INLINE_JSONB"
    assert row[1] is None
    assert dict(row[2]) == component.to_canonical_dict()


def test_migration_103_adds_compact_external_outcome_forecast_index(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    assert (migrations[-2].version, migrations[-2].name) == (
        103,
        "historical_outcome_forecast_index",
    )
    PostgresMigrator(migrations=migrations[:102]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations[:103]).apply_all(
        postgres_factory
    )

    assert tuple((item.version, item.name) for item in applied) == (
        (103, "historical_outcome_forecast_index"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        table = connection.execute(
            "SELECT to_regclass('historical_corpus_outcome_forecast_index')"
        ).fetchone()
        definitions = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_catalog.pg_constraint
                WHERE conrelid =
                    'historical_corpus_outcome_forecast_index'::regclass
                ORDER BY conname
                """
            ).fetchall()
        )
        trigger = connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_trigger
            WHERE tgrelid =
                'historical_corpus_outcome_forecast_index'::regclass
              AND tgname =
                'historical_corpus_outcome_forecast_index_no_update'
              AND NOT tgisinternal
            """
        ).fetchone()
    assert table == ("historical_corpus_outcome_forecast_index",)
    assert any(
        "FOREIGN KEY (component_id, component_hash, trading_date)" in item
        for item in definitions
    )
    assert trigger == (1,)


def test_migration_104_indexes_external_outcome_owner_foreign_key(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    migration_104 = tuple(item for item in migrations if item.version <= 104)
    assert (migration_104[-1].version, migration_104[-1].name) == (
        104,
        "historical_outcome_forecast_fk_index",
    )
    PostgresMigrator(migrations=migrations[:103]).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migration_104).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in applied) == (
        (104, "historical_outcome_forecast_fk_index"),
    )
    with postgres_factory.connection(read_only=True) as connection:
        definition = connection.execute(
            """
            SELECT pg_get_indexdef(index_record.indexrelid)
            FROM pg_catalog.pg_index AS index_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = index_record.indexrelid
            WHERE relation.relname =
                'historical_corpus_outcome_forecast_owner_fk_idx'
            """
        ).fetchone()
    assert definition is not None
    assert "(component_id, component_hash, trading_date)" in str(definition[0])


def test_migration_105_upgrades_104_with_typed_target_semantics_and_failures(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    migrations = load_packaged_migrations()
    migration_104 = tuple(item for item in migrations if item.version <= 104)
    PostgresMigrator(migrations=migration_104).apply_all(postgres_factory)

    applied = PostgresMigrator(migrations=migrations).apply_all(postgres_factory)
    repeated = PostgresMigrator(migrations=migrations).apply_all(postgres_factory)

    assert tuple((item.version, item.name) for item in applied) == (
        (105, "alpha_correctness_target_semantics"),
    )
    assert repeated == ()
    with postgres_factory.connection(read_only=True) as connection:
        columns = connection.execute(
            """
            SELECT column_name, is_generated
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'historical_corpus_outcome_label'
              AND column_name IN (
                  'label_schema_version', 'semantic_specification_id',
                  'decision_reference_status', 'outcome_window_status',
                  'checkpoint_observation_status',
                  'checkpoint_return_status', 'mfe_status', 'mae_status',
                  'barrier_status'
              )
            ORDER BY column_name
            """
        ).fetchall()
        tables = connection.execute(
            """
            SELECT tablename FROM pg_catalog.pg_tables
            WHERE schemaname = current_schema()
              AND tablename LIKE 'alpha_correctness_failure_%'
            ORDER BY tablename
            """
        ).fetchall()
        triggers = connection.execute(
            """
            SELECT relation.relname, trigger_record.tgname
            FROM pg_catalog.pg_trigger AS trigger_record
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_record.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE relation.relname LIKE 'alpha_correctness_failure_%'
              AND namespace.nspname = current_schema()
              AND NOT trigger_record.tgisinternal
            ORDER BY relation.relname, trigger_record.tgname
            """
        ).fetchall()
        latest = connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone()
    assert columns == [
        ("barrier_status", "ALWAYS"),
        ("checkpoint_observation_status", "ALWAYS"),
        ("checkpoint_return_status", "ALWAYS"),
        ("decision_reference_status", "ALWAYS"),
        ("label_schema_version", "ALWAYS"),
        ("mae_status", "ALWAYS"),
        ("mfe_status", "ALWAYS"),
        ("outcome_window_status", "ALWAYS"),
        ("semantic_specification_id", "ALWAYS"),
    ]
    assert tables == [
        ("alpha_correctness_failure_detail",),
        ("alpha_correctness_failure_index",),
        ("alpha_correctness_failure_source_binding",),
    ]
    assert triggers == [
        (
            "alpha_correctness_failure_detail",
            "alpha_correctness_failure_detail_no_update",
        ),
        (
            "alpha_correctness_failure_index",
            "alpha_correctness_failure_index_no_update",
        ),
        (
            "alpha_correctness_failure_source_binding",
            "alpha_correctness_failure_source_binding_no_update",
        ),
    ]
    assert latest == (105,)
