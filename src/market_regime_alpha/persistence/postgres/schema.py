"""Catalog verification for the complete PostgreSQL authority schema."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

import psycopg


EXPECTED_AUTHORITY_TABLES: Final[frozenset[str]] = frozenset(
    {
        "schema_migrations",
        "governance_commands",
        "model_registrations",
        "model_lifecycle_transitions",
        "model_governance_action",
        "model_version_lineage",
        "model_qualification_evidence",
        "model_governance_policy",
        "model_qualification_decision",
        "model_runtime_lineage",
        "model_runtime_assignment",
        "model_selection_receipt",
        "pit_authority_action",
        "pit_artifact_authority_resolution",
        "pit_source_qualification",
        "pit_source_qualification_evidence",
        "pit_fact_revision",
        "pit_fact_temporal_authority_resolution",
        "pit_as_of_snapshot",
        "formal_pit_validation_evidence",
        "governed_experiments",
        "experiment_access_events",
        "decision_commands",
        "trading_opportunities",
        "opportunity_events",
        "trading_theses",
        "thesis_events",
        "portfolio_risk_commands",
        "portfolio_decisions",
        "risk_decisions",
        "execution_commands",
        "manual_trade_records",
        "manual_trade_events",
        "manual_fills",
        "complete_account_risk_commands",
        "authoritative_account_portfolio_snapshots",
        "complete_account_portfolio_decisions",
        "complete_account_risk_decisions",
        "position_books",
        "position_book_events",
        "traceable_manual_trade_bindings",
        "risk_reducing_decisions",
        "risk_reducing_commands",
        "thesis_health_observations",
        "thesis_health_commands",
        "composite_operational_manifests",
        "composite_operational_components",
        "composite_operational_field_authorities",
        "composite_operational_commands",
        "operational_exit_directives",
        "risk_reduction_confirmation_attempts",
        "risk_reduction_confirmation_commands",
        "risk_reducing_manual_trade_bindings",
        "lifecycle_runs",
        "lifecycle_stages",
        "lifecycle_attempts",
        "lifecycle_stage_receipts",
        "lifecycle_events",
        "feature_materialization_run",
        "feature_materialization_task",
        "feature_materialization_attempt",
        "feature_materialization_receipt",
        "feature_materialization_event",
        "controlled_operation_run",
        "controlled_operation_stage",
        "controlled_operation_attempt",
        "controlled_operation_receipt",
        "controlled_operation_child_run",
        "controlled_operation_event",
        "longitudinal_operational_index",
        "daily_runs",
        "acquisition_stage_receipts",
        "stage_receipts",
        "runtime_database_bindings",
        "free_data_operation_blocked",
        "continuous_research_run",
        "continuous_runtime_tick",
        "continuous_provider_attempt",
        "continuous_evidence_commit",
        "continuous_current_evidence",
        "continuous_change_decision",
        "continuous_child_run",
        "continuous_runtime_event",
        "continuous_runtime_schedule",
        "market_regime_state_observation",
        "market_regime_state",
        "market_regime_state_transition",
        "etf_rotation_state_observation",
        "etf_rotation_state",
        "etf_rotation_state_transition",
        "theme_rotation_state_observation",
        "theme_rotation_state",
        "theme_rotation_state_transition",
        "capital_state_observation",
        "capital_state",
        "capital_state_transition",
        "state_current_pointer",
        "dynamic_stock_pool",
        "dynamic_stock_pool_member",
        "dynamic_stock_pool_change",
        "state_runtime_receipt",
        "state_runtime_candidate_artifact",
        "state_research_stage_authority",
        "reconciliation_tolerance_configuration",
        "decision_risk_configuration",
        "decision_position_settlement_evidence",
        "decision_fill_account_authority",
        "decision_replay_import",
        "manual_account_observation",
        "manual_position_observation",
        "account_reconciliation",
        "reconciliation_difference",
        "daily_decision_summary",
        "daily_summary_candidate",
        "research_portfolio_proposal",
        "research_portfolio_line",
        "independent_risk_decision",
        "decision_runtime_receipt",
        "research_daily_summary",
        "research_summary_stage",
        "shadow_research_session",
        "shadow_research_decision",
        "shadow_research_event",
        "prospective_outcome_settlement",
    }
)

EXPECTED_AUTHORITY_TRIGGERS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("model_governance_action", "model_governance_action_no_delete"),
        ("model_governance_action", "model_governance_action_no_update"),
        ("model_version_lineage", "model_version_lineage_no_delete"),
        ("model_version_lineage", "model_version_lineage_no_update"),
        ("model_qualification_evidence", "model_qualification_evidence_no_delete"),
        ("model_qualification_evidence", "model_qualification_evidence_no_update"),
        ("model_governance_policy", "model_governance_policy_no_delete"),
        ("model_governance_policy", "model_governance_policy_no_update"),
        ("model_qualification_decision", "model_qualification_decision_no_delete"),
        ("model_qualification_decision", "model_qualification_decision_no_update"),
        ("model_runtime_lineage", "model_runtime_lineage_no_delete"),
        ("model_runtime_lineage", "model_runtime_lineage_no_update"),
        ("model_runtime_assignment", "model_runtime_assignment_no_delete"),
        ("model_runtime_assignment", "model_runtime_assignment_no_update"),
        ("model_selection_receipt", "model_selection_receipt_no_delete"),
        ("model_selection_receipt", "model_selection_receipt_no_update"),
        ("pit_authority_action", "pit_authority_action_no_delete"),
        ("pit_authority_action", "pit_authority_action_no_update"),
        (
            "pit_artifact_authority_resolution",
            "pit_artifact_authority_resolution_no_delete",
        ),
        (
            "pit_artifact_authority_resolution",
            "pit_artifact_authority_resolution_no_update",
        ),
        ("pit_source_qualification", "pit_source_qualification_no_delete"),
        ("pit_source_qualification", "pit_source_qualification_no_update"),
        (
            "pit_source_qualification_evidence",
            "pit_source_qualification_evidence_no_delete",
        ),
        (
            "pit_source_qualification_evidence",
            "pit_source_qualification_evidence_no_update",
        ),
        ("pit_fact_revision", "pit_fact_revision_no_delete"),
        ("pit_fact_revision", "pit_fact_revision_no_update"),
        (
            "pit_fact_temporal_authority_resolution",
            "pit_fact_temporal_authority_resolution_no_delete",
        ),
        (
            "pit_fact_temporal_authority_resolution",
            "pit_fact_temporal_authority_resolution_no_update",
        ),
        ("pit_as_of_snapshot", "pit_as_of_snapshot_no_delete"),
        ("pit_as_of_snapshot", "pit_as_of_snapshot_no_update"),
        ("formal_pit_validation_evidence", "formal_pit_validation_evidence_no_delete"),
        ("formal_pit_validation_evidence", "formal_pit_validation_evidence_no_update"),
        ("account_reconciliation", "account_reconciliation_no_delete"),
        ("account_reconciliation", "account_reconciliation_no_update"),
        ("composite_operational_commands", "composite_operational_commands_no_delete"),
        ("composite_operational_commands", "composite_operational_commands_no_update"),
        ("composite_operational_components", "composite_operational_components_no_delete"),
        ("composite_operational_components", "composite_operational_components_no_update"),
        ("composite_operational_field_authorities", "composite_operational_field_authorities_no_delete"),
        ("composite_operational_field_authorities", "composite_operational_field_authorities_no_update"),
        ("composite_operational_manifests", "composite_operational_manifests_no_delete"),
        ("composite_operational_manifests", "composite_operational_manifests_no_update"),
        ("controlled_operation_attempt", "controlled_operation_attempt_identity_guard"),
        ("controlled_operation_attempt", "controlled_operation_attempts_no_delete"),
        ("controlled_operation_child_run", "controlled_operation_child_runs_no_delete"),
        ("controlled_operation_child_run", "controlled_operation_child_runs_no_update"),
        ("controlled_operation_event", "controlled_operation_events_no_delete"),
        ("controlled_operation_event", "controlled_operation_events_no_update"),
        ("controlled_operation_receipt", "controlled_operation_receipts_no_delete"),
        ("controlled_operation_receipt", "controlled_operation_receipts_no_update"),
        ("controlled_operation_run", "controlled_operation_run_identity_immutable"),
        ("controlled_operation_run", "controlled_operation_runs_no_delete"),
        ("daily_decision_summary", "daily_decision_summary_no_delete"),
        ("daily_decision_summary", "daily_decision_summary_no_update"),
        ("daily_summary_candidate", "daily_summary_candidate_no_delete"),
        ("daily_summary_candidate", "daily_summary_candidate_no_update"),
        ("decision_runtime_receipt", "decision_runtime_receipt_no_delete"),
        ("decision_runtime_receipt", "decision_runtime_receipt_no_update"),
        ("decision_runtime_receipt", "decision_runtime_receipt_v2_insert_guard"),
        ("research_daily_summary", "research_daily_summary_no_delete"),
        ("research_daily_summary", "research_daily_summary_no_update"),
        ("research_summary_stage", "research_summary_stage_no_delete"),
        ("research_summary_stage", "research_summary_stage_no_update"),
        ("shadow_research_session", "shadow_research_session_guard"),
        ("shadow_research_decision", "shadow_research_decision_no_update"),
        ("shadow_research_event", "shadow_research_event_no_update"),
        (
            "prospective_outcome_settlement",
            "prospective_outcome_settlement_no_update",
        ),
        ("controlled_operation_stage", "controlled_operation_completed_stage_immutable"),
        ("controlled_operation_stage", "controlled_operation_stages_no_delete"),
        ("continuous_research_run", "continuous_research_run_identity_immutable"),
        ("continuous_research_run", "continuous_research_run_no_delete"),
        ("continuous_runtime_tick", "continuous_runtime_tick_no_delete"),
        ("continuous_runtime_tick", "continuous_runtime_tick_terminal_immutable"),
        ("continuous_provider_attempt", "continuous_provider_attempt_no_delete"),
        ("continuous_provider_attempt", "continuous_provider_attempt_transition_guard"),
        ("continuous_evidence_commit", "continuous_evidence_commit_no_update"),
        ("continuous_evidence_commit", "continuous_evidence_commit_no_delete"),
        ("continuous_current_evidence", "continuous_current_evidence_no_delete"),
        ("continuous_current_evidence", "continuous_current_evidence_transition_guard"),
        ("continuous_change_decision", "continuous_change_decision_no_update"),
        ("continuous_change_decision", "continuous_change_decision_no_delete"),
        ("continuous_child_run", "continuous_child_run_no_update"),
        ("continuous_child_run", "continuous_child_run_no_delete"),
        ("continuous_runtime_event", "continuous_runtime_event_no_update"),
        ("continuous_runtime_event", "continuous_runtime_event_no_delete"),
        ("continuous_runtime_schedule", "continuous_runtime_schedule_identity_immutable"),
        ("continuous_runtime_schedule", "continuous_runtime_schedule_no_delete"),
        ("market_regime_state_observation", "market_regime_state_observation_no_update"),
        ("market_regime_state_observation", "market_regime_state_observation_no_delete"),
        ("market_regime_state", "market_regime_state_no_update"),
        ("market_regime_state", "market_regime_state_no_delete"),
        ("market_regime_state_transition", "market_regime_state_transition_no_update"),
        ("market_regime_state_transition", "market_regime_state_transition_no_delete"),
        ("etf_rotation_state_observation", "etf_rotation_state_observation_no_update"),
        ("etf_rotation_state_observation", "etf_rotation_state_observation_no_delete"),
        ("etf_rotation_state", "etf_rotation_state_no_update"),
        ("etf_rotation_state", "etf_rotation_state_no_delete"),
        ("etf_rotation_state_transition", "etf_rotation_state_transition_no_update"),
        ("etf_rotation_state_transition", "etf_rotation_state_transition_no_delete"),
        ("theme_rotation_state_observation", "theme_rotation_state_observation_no_update"),
        ("theme_rotation_state_observation", "theme_rotation_state_observation_no_delete"),
        ("theme_rotation_state", "theme_rotation_state_no_update"),
        ("theme_rotation_state", "theme_rotation_state_no_delete"),
        ("theme_rotation_state_transition", "theme_rotation_state_transition_no_update"),
        ("theme_rotation_state_transition", "theme_rotation_state_transition_no_delete"),
        ("capital_state_observation", "capital_state_observation_no_update"),
        ("capital_state_observation", "capital_state_observation_no_delete"),
        ("capital_state", "capital_state_no_update"),
        ("capital_state", "capital_state_no_delete"),
        ("capital_state_transition", "capital_state_transition_no_update"),
        ("capital_state_transition", "capital_state_transition_no_delete"),
        ("state_current_pointer", "state_current_pointer_no_delete"),
        ("state_current_pointer", "state_current_pointer_cas_guard"),
        ("dynamic_stock_pool", "dynamic_stock_pool_no_update"),
        ("dynamic_stock_pool", "dynamic_stock_pool_no_delete"),
        ("dynamic_stock_pool_member", "dynamic_stock_pool_member_no_update"),
        ("dynamic_stock_pool_member", "dynamic_stock_pool_member_no_delete"),
        ("dynamic_stock_pool_change", "dynamic_stock_pool_change_no_update"),
        ("dynamic_stock_pool_change", "dynamic_stock_pool_change_no_delete"),
        ("state_runtime_receipt", "state_runtime_receipt_no_update"),
        ("state_runtime_receipt", "state_runtime_receipt_no_delete"),
        ("state_runtime_candidate_artifact", "state_runtime_candidate_artifact_no_update"),
        ("state_runtime_candidate_artifact", "state_runtime_candidate_artifact_no_delete"),
        ("state_research_stage_authority", "state_research_stage_authority_no_update"),
        ("state_research_stage_authority", "state_research_stage_authority_no_delete"),
        ("reconciliation_tolerance_configuration", "reconciliation_tolerance_configuration_no_update"),
        ("reconciliation_tolerance_configuration", "reconciliation_tolerance_configuration_no_delete"),
        ("decision_risk_configuration", "decision_risk_configuration_no_update"),
        ("decision_risk_configuration", "decision_risk_configuration_no_delete"),
        ("decision_position_settlement_evidence", "decision_position_settlement_evidence_no_update"),
        ("decision_position_settlement_evidence", "decision_position_settlement_evidence_no_delete"),
        ("decision_fill_account_authority", "decision_fill_account_authority_no_update"),
        ("decision_fill_account_authority", "decision_fill_account_authority_no_delete"),
        ("decision_replay_import", "decision_replay_import_no_update"),
        ("decision_replay_import", "decision_replay_import_no_delete"),
        ("feature_materialization_attempt", "feature_materialization_attempt_transition_guard"),
        ("feature_materialization_attempt", "feature_materialization_attempts_no_delete"),
        ("feature_materialization_event", "feature_materialization_events_no_delete"),
        ("feature_materialization_event", "feature_materialization_events_no_update"),
        ("feature_materialization_receipt", "feature_materialization_receipts_no_delete"),
        ("feature_materialization_receipt", "feature_materialization_receipts_no_update"),
        ("feature_materialization_run", "feature_materialization_run_identity_immutable"),
        ("feature_materialization_run", "feature_materialization_runs_no_delete"),
        ("feature_materialization_task", "feature_materialization_completed_tasks_immutable"),
        ("feature_materialization_task", "feature_materialization_tasks_no_delete"),
        ("lifecycle_attempts", "lifecycle_attempts_completion_only"),
        ("lifecycle_attempts", "lifecycle_attempts_no_delete"),
        ("lifecycle_events", "lifecycle_events_no_delete"),
        ("lifecycle_events", "lifecycle_events_no_update"),
        ("lifecycle_runs", "lifecycle_runs_identity_immutable"),
        ("lifecycle_runs", "lifecycle_runs_no_delete"),
        ("lifecycle_stage_receipts", "lifecycle_stage_receipts_no_delete"),
        ("lifecycle_stage_receipts", "lifecycle_stage_receipts_no_update"),
        ("lifecycle_stages", "lifecycle_stages_no_delete"),
        ("lifecycle_stages", "lifecycle_terminal_stages_immutable"),
        ("longitudinal_operational_index", "longitudinal_operational_no_delete"),
        ("longitudinal_operational_index", "longitudinal_operational_no_update"),
        ("manual_fills", "manual_fills_no_delete"),
        ("manual_fills", "manual_fills_no_update"),
        ("manual_account_observation", "manual_account_observation_no_delete"),
        ("manual_account_observation", "manual_account_observation_no_update"),
        ("manual_position_observation", "manual_position_observation_no_delete"),
        ("manual_position_observation", "manual_position_observation_no_update"),
        ("independent_risk_decision", "independent_risk_decision_no_delete"),
        ("independent_risk_decision", "independent_risk_decision_no_update"),
        ("reconciliation_difference", "reconciliation_difference_no_delete"),
        ("reconciliation_difference", "reconciliation_difference_no_update"),
        ("research_portfolio_line", "research_portfolio_line_no_delete"),
        ("research_portfolio_line", "research_portfolio_line_no_update"),
        ("research_portfolio_proposal", "research_portfolio_proposal_no_delete"),
        ("research_portfolio_proposal", "research_portfolio_proposal_no_update"),
        ("runtime_database_bindings", "runtime_database_bindings_no_delete"),
        ("runtime_database_bindings", "runtime_database_bindings_no_update"),
        ("free_data_operation_blocked", "free_data_operation_blocked_no_delete"),
        ("free_data_operation_blocked", "free_data_operation_blocked_no_update"),
        ("operational_exit_directives", "operational_exit_directives_no_delete"),
        ("operational_exit_directives", "operational_exit_directives_no_update"),
        ("risk_reducing_commands", "risk_reducing_commands_no_delete"),
        ("risk_reducing_commands", "risk_reducing_commands_no_update"),
        ("risk_reducing_decisions", "risk_reducing_decisions_no_delete"),
        ("risk_reducing_decisions", "risk_reducing_decisions_no_update"),
        ("risk_reducing_manual_trade_bindings", "risk_reducing_manual_trade_binding_route_guard"),
        ("risk_reducing_manual_trade_bindings", "risk_reducing_manual_trade_bindings_no_delete"),
        ("risk_reducing_manual_trade_bindings", "risk_reducing_manual_trade_bindings_no_update"),
        ("risk_reduction_confirmation_attempts", "risk_reduction_confirmation_attempts_no_delete"),
        ("risk_reduction_confirmation_attempts", "risk_reduction_confirmation_attempts_no_update"),
        ("risk_reduction_confirmation_commands", "risk_reduction_confirmation_commands_no_delete"),
        ("risk_reduction_confirmation_commands", "risk_reduction_confirmation_commands_no_update"),
        ("thesis_health_commands", "thesis_health_commands_no_delete"),
        ("thesis_health_commands", "thesis_health_commands_no_update"),
        ("thesis_health_observations", "thesis_health_observations_no_delete"),
        ("thesis_health_observations", "thesis_health_observations_no_update"),
        ("traceable_manual_trade_bindings", "traceable_manual_trade_binding_route_guard"),
        ("traceable_manual_trade_bindings", "traceable_manual_trade_bindings_no_delete"),
        ("traceable_manual_trade_bindings", "traceable_manual_trade_bindings_no_update"),
    }
)


class PostgresSchemaError(RuntimeError):
    """Raised when catalog evidence differs from authoritative expectations."""


def verify_postgres_authority_schema(
    connection: psycopg.Connection[Any],
) -> None:
    rows = connection.execute(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = current_schema()
        """
    ).fetchall()
    actual = {str(row[0]) for row in rows}
    missing = EXPECTED_AUTHORITY_TABLES - actual
    unexpected = actual - EXPECTED_AUTHORITY_TABLES
    if missing:
        raise PostgresSchemaError(f"missing tables: {sorted(missing)}")
    if unexpected:
        raise PostgresSchemaError(f"unexpected tables: {sorted(unexpected)}")
    _verify_primary_keys(connection, EXPECTED_AUTHORITY_TABLES)
    _verify_foreign_key_indexes(connection)
    _verify_triggers(connection)


def _verify_primary_keys(
    connection: psycopg.Connection[Any],
    tables: Iterable[str],
) -> None:
    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.table_constraints
        WHERE table_schema = current_schema()
          AND constraint_type = 'PRIMARY KEY'
        """
    ).fetchall()
    present = {str(row[0]) for row in rows}
    missing = set(tables) - present
    if missing:
        raise PostgresSchemaError(
            f"tables without primary keys: {sorted(missing)}"
        )


def _verify_foreign_key_indexes(connection: psycopg.Connection[Any]) -> None:
    rows = connection.execute(
        """
        SELECT relation.relname, constraint_record.conname
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND constraint_record.contype = 'f'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_index AS index_record
              WHERE index_record.indrelid = constraint_record.conrelid
                AND index_record.indisvalid
                AND (
                    SELECT array_agg(index_key.attnum ORDER BY index_key.ordinality)
                    FROM unnest(index_record.indkey::smallint[])
                        WITH ORDINALITY AS index_key(attnum, ordinality)
                    WHERE index_key.ordinality
                        <= cardinality(constraint_record.conkey)
                ) = constraint_record.conkey
          )
        """
    ).fetchall()
    if rows:
        formatted = [f"{row[0]}.{row[1]}" for row in rows]
        raise PostgresSchemaError(
            f"foreign keys without supporting indexes: {formatted}"
        )


def _verify_triggers(connection: psycopg.Connection[Any]) -> None:
    rows = connection.execute(
        """
        SELECT event_object_table, trigger_name
        FROM information_schema.triggers
        WHERE trigger_schema = current_schema()
        """
    ).fetchall()
    actual = {(str(row[0]), str(row[1])) for row in rows}
    missing = EXPECTED_AUTHORITY_TRIGGERS - actual
    unexpected = actual - EXPECTED_AUTHORITY_TRIGGERS
    if missing:
        raise PostgresSchemaError(f"missing triggers: {sorted(missing)}")
    if unexpected:
        raise PostgresSchemaError(f"unexpected triggers: {sorted(unexpected)}")
