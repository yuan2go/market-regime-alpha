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
        "state_policy_authority",
        "state_series",
        "state_series_link",
        "state_series_head",
        "outcome_target_protocol",
        "outcome_target_definition",
        "targeted_shadow_outcome",
        "targeted_shadow_outcome_label",
        "prospective_evidence_attestation",
        "research_evaluation_panel_v2",
        "research_evaluation_panel_slice_v2",
        "research_evaluation_panel_row_v2",
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
        "shadow_research_decision_state_policy",
        "shadow_research_event",
        "prospective_outcome_settlement",
        "research_evaluation_dataset",
        "research_evaluation_dataset_settlement",
        "etf_theme_reference_snapshot",
        "research_validation_artifact",
        "research_panel_factor_exposure",
        "historical_path_sample_record",
        "calibration_partition_binding",
        "strategy_shadow_session",
        "strategy_shadow_event",
        "strategy_shadow_artifact",
        "strategy_shadow_policy_authority",
        "entry_holding_exit_qualification_policy",
        "strategy_shadow_portfolio",
        "strategy_shadow_portfolio_day",
        "continuous_runtime_authority_evidence",
        "free_data_research_universe_snapshot",
        "free_data_research_universe_member",
        "security_principal",
        "security_principal_status_event",
        "security_role_event",
        "security_approval",
        "security_approval_decision",
        "security_audit_event",
        "security_governance_command",
        "formal_research_protocol",
        "formal_research_protocol_component",
        "outcome_target_bound_forecast",
        "outcome_target_bound_forecast_estimate",
        "provider_fact_qualification_policy",
        "provider_fact_qualification_decision",
        "provider_fact_qualification_command",
        "formal_oos_qualification_policy",
        "formal_evaluation_observation_set",
        "formal_evaluation_observation_binding",
        "historical_sample_qualification_decision",
        "formal_oos_qualification_decision",
        "research_qualification_command",
        "calibration_qualification_policy",
        "formal_calibration_observation_binding",
        "calibration_qualification_decision",
        "calibration_qualification_command",
        "prospective_shadow_qualification_policy",
        "phase_c_stage_decision",
        "production_admission_decision_authority",
        "phase_c_gate_command",
        "pit_trading_calendar_canonical_snapshot",
        "formal_research_protocol_component_owner_resolution",
        "locked_oos_evidence_consumption",
        "frozen_hypothesis_family",
        "frozen_hypothesis_family_target",
        "formal_research_protocol_historical_dataset",
        "historical_sample_qualification_pit_evidence",
        "historical_sample_qualification_forecast_receipt",
        "formal_oos_qualification_historical_decision",
        "formal_oos_qualification_pit_evidence",
        "formal_forecast_computation_receipt",
        "research_model_training_request",
        "research_model_training_sample",
        "research_model_training_feature",
        "research_model_training_target",
        "research_model_walk_forward_fold",
        "research_model_training_source_binding",
        "research_model_artifact",
        "research_model_candidate_diagnostic",
        "research_model_coefficient_head",
        "research_model_inference_receipt",
        "research_model_inference_source_binding",
        "research_universe_policy",
        "runtime_scope_receipt",
        "runtime_scope_input_reference",
        "runtime_scope_member",
        "runtime_scope_operational_input",
        "historical_research_run",
        "historical_research_session",
        "historical_research_stage_receipt",
        "historical_research_attempt",
        "historical_research_event",
        "shadow_observation_policy",
        "shadow_observation_receipt",
        "shadow_observation_value",
        "shadow_observation_source_binding",
        "shadow_performance_policy",
        "shadow_performance_report",
        "shadow_performance_state_binding",
        "shadow_performance_metric",
        "shadow_performance_period_return",
        "shadow_performance_attribution",
        "strategy_shadow_session_lineage_binding",
        "strategy_shadow_portfolio_state_source_binding",
        "formal_forecast_computation_command",
        "locked_oos_raw_evidence_unlock",
        "locked_oos_target_observation_consumption",
        "formal_hypothesis_family_evaluation",
        "formal_hypothesis_family_evaluation_target",
        "formal_hypothesis_family_evaluation_pit_evidence",
        "formal_hypothesis_family_evaluation_historical_decision",
        "phase_c_formal_operator_command",
        "formal_locked_oos_roster",
        "formal_locked_oos_roster_member",
        "pit_universe_membership_projection",
        "pit_universe_membership_projection_member",
        "formal_locked_oos_roster_universe_binding",
        "formal_execution_request",
        "formal_execution_provider_requirement",
        "formal_execution_assessment",
        "formal_execution_stage_assessment",
        "formal_execution_source_binding",
        "historical_corpus_owner",
        "historical_corpus_partition",
        "historical_corpus_session_component",
        "historical_corpus_component_source_binding",
        "historical_research_evidence",
        "historical_research_evidence_metric",
    }
)

EXPECTED_AUTHORITY_TRIGGERS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
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
        *(
            (table_name, f"{table_name}_no_update")
            for table_name in (
                "research_model_training_request",
                "research_model_training_sample",
                "research_model_training_feature",
                "research_model_training_target",
                "research_model_walk_forward_fold",
                "research_model_training_source_binding",
                "research_model_artifact",
                "research_model_candidate_diagnostic",
                "research_model_coefficient_head",
                "research_model_inference_receipt",
                "research_model_inference_source_binding",
            )
        ),
        *(
            (table_name, f"{table_name}_no_update")
            for table_name in (
                "research_universe_policy",
                "runtime_scope_receipt",
                "runtime_scope_input_reference",
                "runtime_scope_member",
                "runtime_scope_operational_input",
                "historical_research_stage_receipt",
                "historical_research_event",
                "shadow_observation_policy",
                "shadow_observation_receipt",
                "shadow_observation_value",
                "shadow_observation_source_binding",
                "shadow_performance_policy",
                "shadow_performance_report",
                "shadow_performance_state_binding",
                "shadow_performance_metric",
                "shadow_performance_period_return",
                "shadow_performance_attribution",
                "strategy_shadow_session_lineage_binding",
                "strategy_shadow_portfolio_state_source_binding",
                "historical_corpus_owner",
                "historical_corpus_partition",
                "historical_corpus_session_component",
                "historical_corpus_component_source_binding",
                "historical_research_evidence",
                "historical_research_evidence_metric",
            )
        ),
        (
            "historical_research_run",
            "historical_research_run_identity_immutable",
        ),
        ("historical_research_run", "historical_research_run_no_delete"),
        (
            "historical_research_session",
            "historical_research_session_identity_immutable",
        ),
        ("historical_research_session", "historical_research_session_no_delete"),
        ("historical_research_attempt", "historical_research_attempt_no_delete"),
        ("formal_locked_oos_roster", "formal_locked_oos_roster_no_update"),
        (
            "formal_locked_oos_roster_member",
            "formal_locked_oos_roster_member_no_update",
        ),
        ("formal_execution_request", "formal_execution_request_no_update"),
        (
            "formal_execution_provider_requirement",
            "formal_execution_provider_requirement_no_update",
        ),
        (
            "formal_execution_assessment",
            "formal_execution_assessment_no_update",
        ),
        (
            "formal_execution_stage_assessment",
            "formal_execution_stage_assessment_no_update",
        ),
        (
            "formal_execution_source_binding",
            "formal_execution_source_binding_no_update",
        ),
        ("formal_research_protocol", "formal_research_protocol_no_update"),
        (
            "outcome_target_bound_forecast",
            "outcome_target_bound_forecast_no_update",
        ),
        (
            "outcome_target_bound_forecast_estimate",
            "outcome_target_bound_forecast_estimate_no_update",
        ),
        (
            "provider_fact_qualification_policy",
            "provider_fact_qualification_policy_no_update",
        ),
        (
            "provider_fact_qualification_decision",
            "provider_fact_qualification_decision_no_update",
        ),
        (
            "provider_fact_qualification_command",
            "provider_fact_qualification_command_no_update",
        ),
        (
            "formal_oos_qualification_policy",
            "formal_oos_qualification_policy_no_update",
        ),
        (
            "formal_evaluation_observation_set",
            "formal_evaluation_observation_set_no_update",
        ),
        (
            "formal_evaluation_observation_binding",
            "formal_evaluation_observation_binding_no_update",
        ),
        (
            "historical_sample_qualification_decision",
            "historical_sample_qualification_decision_no_update",
        ),
        (
            "formal_oos_qualification_decision",
            "formal_oos_qualification_decision_no_update",
        ),
        (
            "research_qualification_command",
            "research_qualification_command_no_update",
        ),
        (
            "calibration_qualification_policy",
            "calibration_qualification_policy_no_update",
        ),
        (
            "formal_calibration_observation_binding",
            "formal_calibration_observation_binding_no_update",
        ),
        (
            "calibration_qualification_decision",
            "calibration_qualification_decision_no_update",
        ),
        (
            "calibration_qualification_command",
            "calibration_qualification_command_no_update",
        ),
        (
            "prospective_shadow_qualification_policy",
            "prospective_shadow_qualification_policy_no_update",
        ),
        (
            "phase_c_stage_decision",
            "phase_c_stage_decision_no_update",
        ),
        (
            "production_admission_decision_authority",
            "production_admission_decision_authority_no_update",
        ),
        (
            "phase_c_gate_command",
            "phase_c_gate_command_no_update",
        ),
        (
            "pit_trading_calendar_canonical_snapshot",
            "pit_trading_calendar_canonical_snapshot_no_update",
        ),
        (
            "formal_research_protocol_component_owner_resolution",
            "formal_research_protocol_component_owner_resolution_no_update",
        ),
        (
            "locked_oos_evidence_consumption",
            "locked_oos_evidence_consumption_no_update",
        ),
        (
            "frozen_hypothesis_family",
            "frozen_hypothesis_family_no_update",
        ),
        (
            "frozen_hypothesis_family_target",
            "frozen_hypothesis_family_target_no_update",
        ),
        (
            "formal_research_protocol_historical_dataset",
            "formal_research_protocol_historical_dataset_no_update",
        ),
        (
            "historical_sample_qualification_pit_evidence",
            "historical_sample_qualification_pit_evidence_no_update",
        ),
        (
            "historical_sample_qualification_forecast_receipt",
            "historical_sample_qualification_forecast_receipt_no_update",
        ),
        (
            "formal_oos_qualification_historical_decision",
            "formal_oos_qualification_historical_decision_no_update",
        ),
        (
            "formal_oos_qualification_pit_evidence",
            "formal_oos_qualification_pit_evidence_no_update",
        ),
        (
            "formal_forecast_computation_receipt",
            "formal_forecast_computation_receipt_no_update",
        ),
        (
            "formal_forecast_computation_command",
            "formal_forecast_computation_command_no_update",
        ),
        (
            "locked_oos_raw_evidence_unlock",
            "locked_oos_raw_evidence_unlock_no_update",
        ),
        (
            "locked_oos_target_observation_consumption",
            "locked_oos_target_observation_consumption_no_update",
        ),
        (
            "formal_hypothesis_family_evaluation",
            "formal_hypothesis_family_evaluation_no_update",
        ),
        (
            "formal_hypothesis_family_evaluation_target",
            "formal_hypothesis_family_evaluation_target_no_update",
        ),
        (
            "formal_hypothesis_family_evaluation_pit_evidence",
            "formal_hypothesis_family_evaluation_pit_evidence_no_update",
        ),
        (
            "formal_hypothesis_family_evaluation_historical_decision",
            "formal_family_evaluation_historical_decision_no_update",
        ),
        (
            "phase_c_formal_operator_command",
            "phase_c_formal_operator_command_no_update",
        ),
        ("security_principal", "security_principal_no_update"),
        (
            "security_principal_status_event",
            "security_principal_status_event_no_update",
        ),
        ("security_role_event", "security_role_event_no_update"),
        ("security_approval", "security_approval_no_update"),
        (
            "security_approval_decision",
            "security_approval_decision_no_update",
        ),
        ("security_audit_event", "security_audit_event_no_update"),
        (
            "security_governance_command",
            "security_governance_command_no_update",
        ),
        (
            "strategy_shadow_portfolio",
            "strategy_shadow_portfolio_no_update",
        ),
        (
            "strategy_shadow_portfolio_day",
            "strategy_shadow_portfolio_day_no_update",
        ),
        (
            "free_data_research_universe_snapshot",
            "free_data_research_universe_snapshot_no_update",
        ),
        (
            "free_data_research_universe_member",
            "free_data_research_universe_member_no_update",
        ),
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
        (
            "shadow_research_decision_state_policy",
            "shadow_decision_state_policy_no_update",
        ),
        (
            "shadow_research_decision_state_policy",
            "shadow_decision_state_policy_no_delete",
        ),
        ("shadow_research_event", "shadow_research_event_no_update"),
        (
            "prospective_outcome_settlement",
            "prospective_outcome_settlement_no_update",
        ),
        (
            "research_evaluation_dataset",
            "research_evaluation_dataset_no_update",
        ),
        (
            "research_evaluation_dataset_settlement",
            "research_evaluation_dataset_settlement_no_update",
        ),
        (
            "etf_theme_reference_snapshot",
            "etf_theme_reference_snapshot_no_update",
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
        ("state_policy_authority", "state_policy_authority_no_update"),
        ("state_policy_authority", "state_policy_authority_no_delete"),
        ("state_series", "state_series_no_update"),
        ("state_series", "state_series_no_delete"),
        ("state_series_link", "state_series_link_no_update"),
        ("state_series_link", "state_series_link_no_delete"),
        ("state_series_head", "state_series_head_no_delete"),
        ("state_series_head", "state_series_head_cas_guard"),
        ("outcome_target_protocol", "outcome_target_protocol_no_update"),
        ("outcome_target_protocol", "outcome_target_protocol_no_delete"),
        ("outcome_target_definition", "outcome_target_definition_no_update"),
        ("outcome_target_definition", "outcome_target_definition_no_delete"),
        ("targeted_shadow_outcome", "targeted_shadow_outcome_no_update"),
        ("targeted_shadow_outcome", "targeted_shadow_outcome_no_delete"),
        ("targeted_shadow_outcome_label", "targeted_shadow_outcome_label_no_update"),
        ("targeted_shadow_outcome_label", "targeted_shadow_outcome_label_no_delete"),
        ("prospective_evidence_attestation", "prospective_evidence_attestation_no_update"),
        ("prospective_evidence_attestation", "prospective_evidence_attestation_no_delete"),
        (
            "formal_research_protocol_component",
            "formal_research_protocol_component_no_update",
        ),
        ("research_evaluation_panel_v2", "research_evaluation_panel_v2_no_update"),
        ("research_evaluation_panel_v2", "research_evaluation_panel_v2_no_delete"),
        ("research_evaluation_panel_slice_v2", "research_evaluation_panel_slice_v2_no_update"),
        ("research_evaluation_panel_slice_v2", "research_evaluation_panel_slice_v2_no_delete"),
        ("research_evaluation_panel_row_v2", "research_evaluation_panel_row_v2_no_update"),
        ("research_evaluation_panel_row_v2", "research_evaluation_panel_row_v2_no_delete"),
        ("research_validation_artifact", "research_validation_artifact_no_update"),
        ("research_validation_artifact", "research_validation_artifact_no_delete"),
        ("research_panel_factor_exposure", "research_panel_factor_exposure_no_update"),
        ("research_panel_factor_exposure", "research_panel_factor_exposure_no_delete"),
        ("historical_path_sample_record", "historical_path_sample_record_no_update"),
        ("historical_path_sample_record", "historical_path_sample_record_no_delete"),
        ("calibration_partition_binding", "calibration_partition_binding_no_update"),
        ("calibration_partition_binding", "calibration_partition_binding_no_delete"),
        ("strategy_shadow_session", "strategy_shadow_session_guard"),
        ("strategy_shadow_session", "strategy_shadow_session_no_delete"),
        ("strategy_shadow_event", "strategy_shadow_event_no_update"),
        ("strategy_shadow_event", "strategy_shadow_event_no_delete"),
        ("strategy_shadow_artifact", "strategy_shadow_artifact_no_update"),
        ("strategy_shadow_artifact", "strategy_shadow_artifact_no_delete"),
        (
            "strategy_shadow_policy_authority",
            "strategy_shadow_policy_authority_no_update",
        ),
        (
            "entry_holding_exit_qualification_policy",
            "entry_holding_exit_qualification_policy_no_update",
        ),
        (
            "entry_holding_exit_qualification_policy",
            "entry_holding_exit_portfolio_policy_owner_guard",
        ),
        ("continuous_runtime_authority_evidence", "continuous_runtime_authority_evidence_no_update"),
        ("continuous_runtime_authority_evidence", "continuous_runtime_authority_evidence_no_delete"),
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
        raise PostgresSchemaError(f"tables without primary keys: {sorted(missing)}")


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
        raise PostgresSchemaError(f"foreign keys without supporting indexes: {formatted}")


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
