from __future__ import annotations

from pathlib import Path

import psycopg

from market_regime_alpha.infrastructure.postgres.schema import (
    EXPECTED_RESEARCH_VALIDITY_TABLES,
    EXPECTED_TARGET_TABLES,
    SchemaManager,
)


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "src/market_regime_alpha/infrastructure/postgres/migrations"


def test_wp11_extends_only_unreleased_baseline() -> None:
    migrations = sorted(item.name for item in MIGRATIONS.glob("*.sql"))
    assert migrations == ["001_baseline.sql"]
    assert len(EXPECTED_RESEARCH_VALIDITY_TABLES) == 12
    assert len(EXPECTED_TARGET_TABLES) == 78


def test_wp11_relations_have_no_generic_or_future_placeholder_shape(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = connection.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'mra'
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (sorted(EXPECTED_RESEARCH_VALIDITY_TABLES),),
        ).fetchall()
        assert not [row for row in columns if row[2] in {"json", "jsonb"}]
        forbidden = {"subject", "subject_id", "subject_kind", "model_id", "forecast_id"}
        assert not [row for row in columns if row[1] in forbidden]
        physical_partitions = connection.execute(
            """
            SELECT child.relname
            FROM pg_inherits
            JOIN pg_class AS child ON child.oid = inhrelid
            JOIN pg_namespace AS namespace ON namespace.oid = child.relnamespace
            WHERE namespace.nspname = 'mra'
              AND child.relname = ANY(%s)
            """,
            (sorted(EXPECTED_RESEARCH_VALIDITY_TABLES),),
        ).fetchall()
        assert physical_partitions == []


def test_access_and_observation_use_concrete_non_nullable_foreign_keys(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        nullable = connection.execute(
            """
            SELECT table_name, column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'mra'
              AND table_name IN (
                  'research_partition_outcome_access',
                  'evaluation_observation'
              )
              AND column_name IN (
                  'evaluation_run_id', 'research_partition_member_id',
                  'market_target_outcome_revision_id', 'outcome_access_id'
              )
            """
        ).fetchall()
        assert nullable
        assert all(row[2] == "NO" for row in nullable)
        constraints = {
            row[0]
            for row in connection.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE connamespace = 'mra'::regnamespace
                  AND conname IN (
                      'research_outcome_access_run_fk',
                      'research_outcome_access_member_fk',
                      'research_outcome_access_revision_fk',
                      'evaluation_observation_access_fk'
                  )
                """
            ).fetchall()
        }
        assert constraints == {
            "research_outcome_access_run_fk",
            "research_outcome_access_member_fk",
            "research_outcome_access_revision_fk",
            "evaluation_observation_access_fk",
        }


def test_wp11_immutable_and_lifecycle_guards_are_installed(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relnamespace = 'mra'::regnamespace
                      AND relname = ANY(%s)
                ) AND NOT tgisinternal
                """,
                (sorted(EXPECTED_RESEARCH_VALIDITY_TABLES),),
            ).fetchall()
        }
        assert {
            "research_partition_overlap_guard",
            "research_partition_member_validate",
            "experiment_partition_closure_guard",
            "experiment_partition_order_guard",
            "experiment_run_order_guard",
            "evaluation_run_open_guard",
            "evaluation_run_transition_guard",
            "research_outcome_access_guard",
            "research_outcome_access_append_only",
            "evaluation_observation_append_only",
            "evaluation_metric_append_only",
            "evaluation_metric_observation_append_only",
        } <= triggers


def test_research_evaluation_resolver_has_no_current_latest_or_market_path() -> None:
    source = (
        ROOT
        / "src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluation_inputs.py"
    ).read_text()
    assert "current_for_commitment" not in source
    assert "ORDER BY revision_ordinal DESC LIMIT 1" not in source
    assert "market_bar_revision" not in source
    assert "provider" not in source.lower()
    assert "supersedes_revision_id" in source
    assert "requested_knowledge_cutoff" in source


def test_partition_closure_and_overlap_are_database_serialized() -> None:
    sql = (MIGRATIONS / "001_baseline.sql").read_text()
    assert "LOCK TABLE mra.decision_target_commitment IN SHARE MODE" in sql
    assert "actual_count <> declared_population_count" in sql
    assert "actual_roster_hash <> NEW.member_roster_sha256" in sql
    assert "decision_reference_research_session_uk" in sql
    assert "research_partition_member_reference_session_fk" in sql
    assert "EXCEPT" in sql
    assert "research-partition-overlap:" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "existing.overlap_policy = 'ISOLATED_PROTECTED'" in sql
    assert "research_partition_decision_start_calendar_fk" in sql
    assert "research_partition_member_session_calendar_fk" in sql
    assert "actual_calendar_count <> NEW.calendar_session_count" in sql
    assert "actual_calendar_hash <> NEW.calendar_roster_sha256" in sql
    assert "session.exchange = NEW.exchange_code" in sql
    assert "existing.exchange_code = NEW.exchange_code" in sql


def test_partition_calendar_authority_is_relational_and_non_nullable(
    target_database_url: str,
) -> None:
    SchemaManager(target_database_url).bootstrap()
    with psycopg.connect(target_database_url) as connection:
        columns = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'mra'
                  AND table_name = 'research_partition'
                  AND column_name IN (
                      'exchange_code', 'timezone_name',
                      'calendar_session_count', 'calendar_roster_sha256'
                  )
                """
            ).fetchall()
        }
        assert columns == {
            "exchange_code": "NO",
            "timezone_name": "NO",
            "calendar_session_count": "NO",
            "calendar_roster_sha256": "NO",
        }


def test_gate_b_and_pit_leaf_selection_are_database_guards() -> None:
    sql = (MIGRATIONS / "001_baseline.sql").read_text()
    assert "protected EvaluationRun requires zero prior Partition access" in sql
    assert "research-protected-access:" in sql
    assert "protected Outcome access must remain first access" in sql
    assert "NEW.settled_at > cutoff" in sql
    assert "Outcome access revision is not the unique visible leaf" in sql
    access_guard = sql.split(
        "CREATE FUNCTION mra.guard_research_outcome_access()", maxsplit=1
    )[1].split("$$;", maxsplit=1)[0]
    assert "FROM mra.market_target_outcome AS root" in access_guard
    assert "FOR SHARE" in access_guard
    assert "cutoff > NEW.accessed_at" in access_guard
    assert "EvaluationRun knowledge cutoff cannot be in the future" in sql


def test_experiment_partition_roster_has_deferred_relational_closure() -> None:
    sql = (MIGRATIONS / "001_baseline.sql").read_text()
    assert "partition_count integer NOT NULL" in sql
    assert "partition_roster_sha256 text NOT NULL" in sql
    assert "binding_ordinal integer NOT NULL" in sql
    assert "experiment_partition_ordinal_uk" in sql
    assert "validate_experiment_partition_closure" in sql
    assert "actual_count <> NEW.partition_count" in sql
    assert "actual_roster_hash <> NEW.partition_roster_sha256" in sql
    assert "Experiment Partition roster is already frozen" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
