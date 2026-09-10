"""Runtime login privileges, independent of cooperative admission locks.

INSERT/UPDATE are restricted to current daily/prospective owner tables. Reference
owners permit UPDATE on one identity column solely for PostgreSQL row locks;
immutable owner triggers still reject modifications. No DELETE or DDL is needed.
The cluster administrator and approved schema publisher remain trusted.
"""

from typing import Any


def _reject_privilege_drift(connection: Any) -> None:
    # Batch effective privileges, including PUBLIC and column grants. Checking
    # ACL rows alone misses inherited grants; table checks alone miss columns.
    row = connection.execute("""
        SELECT EXISTS (SELECT 1 FROM pg_auth_members WHERE member=(
                   SELECT oid FROM pg_roles WHERE rolname=session_user)),
               EXISTS (SELECT 1 FROM pg_namespace WHERE
                   nspname !~ '^pg_' AND nspname <> 'information_schema'
                   AND (has_schema_privilege(oid,'CREATE') OR has_schema_privilege(oid,'USAGE WITH GRANT OPTION'))),
               has_database_privilege(current_database(),'TEMP') OR
               has_database_privilege(current_database(),'CONNECT WITH GRANT OPTION'),
               EXISTS (SELECT 1 FROM pg_class WHERE CASE WHEN relkind='S'
                   THEN has_sequence_privilege(oid,'USAGE,SELECT,UPDATE') ELSE false END)
    """).fetchone()
    if row is None or any(row):
        raise ValueError("DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES: role/schema/temp/sequence")
    rows = connection.execute("""
        SELECT n.nspname,c.relname,p.priv,
               has_table_privilege(c.oid,p.priv || ' WITH GRANT OPTION')
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN unnest(ARRAY['INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p(priv)
        WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname !~ '^pg_'
          AND n.nspname <> 'information_schema' AND has_table_privilege(c.oid,p.priv)
    """).fetchall()
    for schema, table, privilege, grantable in rows:
        if schema != "mra" or table not in WRITE_TABLES or privilege not in ("INSERT", "UPDATE") or grantable:
            raise ValueError(f"DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES: {schema}.{table}:{privilege}")
    if connection.execute("""SELECT EXISTS(SELECT 1 FROM pg_class
            WHERE relkind IN ('r','p','v','m','f')
              AND has_table_privilege(oid,'SELECT WITH GRANT OPTION'))""").fetchone()[0]:
        raise ValueError("DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES: read grant option")
    columns = connection.execute("""
        SELECT n.nspname,c.relname,a.attname,p.priv,
               has_column_privilege(c.oid,a.attnum,p.priv || ' WITH GRANT OPTION')
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        CROSS JOIN unnest(ARRAY['INSERT','UPDATE','REFERENCES']) p(priv)
        WHERE c.relkind IN ('r','p','v','f') AND n.nspname !~ '^pg_'
          AND n.nspname <> 'information_schema'
          AND has_column_privilege(c.oid,a.attnum,p.priv)
          AND (NOT has_table_privilege(c.oid,p.priv)
               OR has_column_privilege(c.oid,a.attnum,p.priv || ' WITH GRANT OPTION'))
    """).fetchall()
    for schema, table, column, privilege, grantable in columns:
        if schema != "mra" or REFERENCE_LOCKS.get(table) != column or privilege != "UPDATE" or grantable:
            raise ValueError(f"DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES: {schema}.{table}.{column}:{privilege}")
    routines = connection.execute("""
        SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
               p.prorettype='trigger'::regtype,p.prosecdef,p.prokind,l.lanname,
               has_function_privilege(p.oid,'EXECUTE WITH GRANT OPTION'),p.pronargs
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_language l ON l.oid=p.prolang
        WHERE has_function_privilege(p.oid,'EXECUTE') AND (
          n.nspname NOT IN ('pg_catalog','information_schema') OR
          EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) acl
                  WHERE acl.grantee=(SELECT oid FROM pg_roles WHERE rolname=session_user)) OR
          has_function_privilege(p.oid,'EXECUTE WITH GRANT OPTION'))
    """).fetchall()
    for schema, name, args, trigger, definer, kind, language, grantable, input_count in routines:
        # Trigger functions cannot be invoked as ordinary functions. All allowed
        # routines execute with invoker permissions; schema/catalog verification
        # binds their released definitions independently of this grant envelope.
        allowed = schema == "mra" and kind == "f" and language in ("sql", "plpgsql") and (trigger or (name, args) in READ_FUNCTIONS)
        allowed |= schema == "pg_catalog" and name == "pg_control_system" and input_count == 0 and kind == "f"
        if not allowed or definer or grantable:
            raise ValueError(f"DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES: routine {schema}.{name}")


WRITE_TABLES = (
    "evaluation_observation",
    "research_partition_outcome_access",
    "decision_run_research_qualification_roster",
    "decision_run_research_qualification_member",
    "artifact",
    "artifact_verification",
    "audit_event",
    "candidate",
    "candidate_score_component",
    "candidate_set",
    "classification",
    "classification_membership_revision",
    "command_receipt",
    "context_assessment",
    "context_metric",
    "context_metric_source",
    "corporate_action_revision",
    "data_capture",
    "dataset",
    "dataset_source",
    "decision_reference_observation",
    "decision_run",
    "decision_run_target",
    "decision_target_commitment",
    "eligibility_assessment",
    "eligibility_reason",
    "evaluation_candidate_outcome_source",
    "evaluation_candidate_source",
    "evaluation_forecast_source",
    "evaluation_formula_parameter",
    "evaluation_metric",
    "evaluation_metric_formula",
    "evaluation_metric_observation",
    "evaluation_protocol",
    "evaluation_protocol_metric",
    "evaluation_run",
    "evaluation_signal_source",
    "experiment",
    "experiment_partition",
    "experiment_run",
    "forecast",
    "forecast_estimate",
    "forecast_model_binding",
    "forecast_run",
    "instrument",
    "instrument_fact_revision",
    "instrument_identifier",
    "market_archive",
    "market_archive_capture_observation",
    "market_archive_resource_stop",
    "market_archive_seal",
    "market_archive_slice",
    "market_archive_slice_gap",
    "market_bar_revision",
    "market_capture_classification_membership_normalization",
    "market_capture_classification_normalization",
    "market_capture_instrument_identifier_normalization",
    "market_capture_instrument_normalization",
    "market_capture_reference_normalization",
    "market_capture_trading_session_normalization",
    "market_target_outcome",
    "market_target_outcome_metric",
    "market_target_outcome_metric_observation",
    "market_target_outcome_metric_reference",
    "market_target_outcome_observation",
    "market_target_outcome_reason",
    "market_target_outcome_revision",
    "market_target_outcome_source",
    "prospective_archive_generation",
    "prospective_archive_generation_member",
    "prospective_archive_planning_gap",
    "prospective_archive_revision_observation",
    "prospective_archive_slice_schedule",
    "prospective_archive_slice_terminal",
    "research_partition",
    "research_partition_member",
    "runtime_attempt",
    "runtime_run",
    "runtime_schedule",
    "runtime_step",
    "runtime_step_dependency",
    "signal",
    "signal_context_binding",
    "signal_run",
    "source_gap",
    "trading_session",
    "universe_member",
    "universe_revision",
)

REFERENCE_LOCKS = {
    "artifact_gc_candidate": "content_sha256",
    "experimental_model_use": "experimental_model_use_id",
    "model": "model_id",
    "model_version": "model_version_id",
    "model_training_run": "model_training_run_id",
    "model_training_reproducibility": "model_training_run_id",
    "target_definition": "target_definition_id",
    "target_checkpoint": "target_definition_id",
    "target_metric_definition": "target_definition_id",
    "target_metric_dependency": "target_definition_id",
    "feature_definition": "feature_definition_id",
    "candidate_policy": "candidate_policy_id",
    "context_policy": "context_policy_id",
    "eligibility_policy": "eligibility_policy_id",
    "strategy_version": "strategy_version_id",
    "universe": "universe_id",
    "provider_product": "provider_product_id",
    "strategy_context_requirement": "strategy_version_id",
    "strategy_signal_rule": "strategy_version_id",
    "strategy_forecast_rule": "strategy_version_id",
    "strategy": "strategy_id",
    "context_policy_metric": "context_policy_id",
    "candidate_policy_component": "candidate_policy_id",
    "exploratory_retrospective_universe_revision": "universe_revision_id",
    "exploratory_retrospective_eligibility_batch": "universe_revision_id",
}

READ_FUNCTIONS = frozenset(
    (
        ("artifact_has_verified_integrity", "integrity_state text, last_verified_at timestamp with time zone"),
        ("canonical_json_text", "value jsonb"),
        ("canonical_sha256", "canonical_text text"),
        ("canonical_timestamptz_text", "value timestamp with time zone"),
        ("context_true_rate", "true_count bigint, available_count bigint"),
        (
            "decision_commitment_content_sha256",
            "candidate_disposition text, candidate_id uuid, decision_reference_observation_id uuid, decision_reference_sha256 text, decision_run_target_id uuid, instrument_id uuid, runtime_mode text, target_definition_id uuid",
        ),
        (
            "decision_qualification_member_content_sha256",
            "decision_code text, experiment_id uuid, qualification_content_sha256 text, qualification_purpose text, revision integer, research_assessment_id uuid, research_qualification_decision_id uuid, research_qualification_policy_id uuid, role text, source_generation_max_decision_time timestamp with time zone, supersedes_decision_id uuid, target_definition_id uuid",
        ),
        (
            "decision_reference_content_sha256",
            "availability_status text, bar_revision integer, bar_revision_id uuid, candidate_id uuid, capture_id uuid, decimal_value numeric, decision_run_target_id uuid, event_end timestamp with time zone, event_start timestamp with time zone, finality_status text, instrument_id uuid, known_at timestamp with time zone, observation_time timestamp with time zone, price_basis text, provider_product_id uuid, source_recorded_at timestamp with time zone, session_id uuid, source_gap_id uuid, source_gap_kind text, source_gap_reason_code text, source_kind text, target_checkpoint_id uuid, timeframe text, value_field text, value_status text",
        ),
        (
            "decision_run_definition_summary_sha256",
            "candidate_count integer, candidate_roster_sha256 text, candidate_set_content_sha256 text, candidate_set_id uuid, commitment_count bigint, commitment_roster_sha256 text, decision_time timestamp with time zone, reference_count bigint, research_purpose text, research_qualification_count integer, research_qualification_roster_sha256 text, request_sha256 text, runtime_mode text, target_count integer, target_roster_sha256 text",
        ),
        (
            "decision_run_target_content_sha256",
            "ordinal integer, provider_id uuid, provider_product_id uuid, provider_product_revision integer, target_checkpoint_id uuid, target_checkpoint_sha256 text, target_definition_id uuid, target_definition_sha256 text, target_version integer",
        ),
        ("experimental_forecast_window_is_open", "decision_id uuid, published_at timestamp with time zone"),
        ("market_artifact_is_readable", "integrity_state text, last_verified_at timestamp with time zone"),
        ("market_capture_normalized_roster", "target_capture_id uuid"),
        ("model_backtest_feature_rosters_match", "requested_model_id uuid, requested_backtest_run_id uuid"),
        ("require_market_authority_capture", "authority_capture_id uuid, authority_kind text"),
        (
            "target_algorithm_binding_sha256",
            "algorithm_code text, algorithm_version text, algorithm_sha256 text, code_artifact_id uuid, code_content_sha256 text, code_size_bytes bigint, config_artifact_id uuid, config_content_sha256 text, config_size_bytes bigint",
        ),
        (
            "target_checkpoint_content_sha256",
            "availability_rule text, checkpoint_code text, finality_rule text, local_time time without time zone, ordinal integer, price_basis text, reference_rule text, checkpoint_role text, session_offset integer, timeframe text, timezone_name text, timing_rule text, value_field text",
        ),
        (
            "target_definition_content_sha256",
            "algorithm_code text, algorithm_version text, algorithm_sha256 text, algorithm_binding_sha256 text, code_artifact_id uuid, code_content_sha256 text, code_size_bytes bigint, config_artifact_id uuid, config_content_sha256 text, config_size_bytes bigint, checkpoint_count integer, checkpoint_roster_sha256 text, dependency_count integer, dependency_roster_sha256 text, instrument_scope text, market_scope text, metric_count integer, metric_roster_sha256 text, registration_status text, supersedes_target_definition_id uuid, target_code text, version integer",
        ),
        (
            "target_metric_content_sha256",
            "algorithm_code text, algorithm_version text, algorithm_sha256 text, algorithm_binding_sha256 text, code_artifact_id uuid, code_content_sha256 text, code_size_bytes bigint, config_artifact_id uuid, config_content_sha256 text, config_size_bytes bigint, barrier_direction text, barrier_threshold numeric, completion_rule text, metric_code text, metric_kind text, ordinal integer, unit text, value_type text",
        ),
        (
            "target_metric_dependency_content_sha256",
            "ordinal integer, dependency_role text, target_checkpoint_id uuid, target_metric_definition_id uuid",
        ),
    )
)


def inspect_runtime_principal(connection: Any) -> dict[str, Any]:
    """Authentication and grants are separate from cooperative advisory admission."""
    row = connection.execute(
        """
        SELECT session_user::text, current_user::text, role.oid::bigint,
               role.rolsuper OR role.rolcreaterole OR role.rolcreatedb
                 OR role.rolreplication OR role.rolbypassrls,
               has_schema_privilege('mra', 'CREATE')
                 OR has_database_privilege(current_database(), 'CREATE'),
               has_table_privilege('mra.runtime_attempt', 'INSERT')
                 AND has_table_privilege('mra.runtime_attempt', 'UPDATE')
                 AND has_table_privilege('mra.runtime_run', 'UPDATE')
                 AND has_table_privilege('mra.runtime_step', 'UPDATE')
                 AND has_table_privilege('mra.command_receipt', 'INSERT')
                 AND has_table_privilege('mra.artifact', 'INSERT')
                 AND has_table_privilege('mra.artifact', 'UPDATE')
                 AND has_table_privilege('mra.decision_run_research_qualification_roster', 'INSERT')
                 AND has_any_column_privilege('mra.decision_run_research_qualification_roster', 'UPDATE')
                 AND has_table_privilege('mra.decision_run_research_qualification_member', 'INSERT')
                 AND has_any_column_privilege('mra.decision_run_research_qualification_member', 'UPDATE')
                 AND has_table_privilege('mra.research_partition_outcome_access', 'INSERT')
                 AND has_any_column_privilege('mra.research_partition_outcome_access', 'UPDATE')
                 AND has_table_privilege('mra.evaluation_observation', 'INSERT')
                 AND has_any_column_privilege('mra.evaluation_observation', 'UPDATE')
                 AND (SELECT bool_and(has_any_column_privilege(name, 'UPDATE'))
                      FROM unnest(%s::text[]) AS required_tables(name)),
               has_table_privilege('mra.schema_migrations', 'INSERT')
                 OR has_table_privilege('mra.model_version', 'INSERT')
                 OR has_table_privilege('mra.provider_qualification_decision', 'INSERT')
                 OR has_table_privilege('mra.research_qualification_decision', 'INSERT')
        FROM pg_roles role WHERE role.rolname = session_user
    """,
        (list("mra." + name for name in REFERENCE_LOCKS),),
    ).fetchone()
    if row is None or row[0] != row[1]:
        raise ValueError("DEPLOYMENT_RUNTIME_PRINCIPAL_IMPERSONATION")
    if row[3] or row[4] or not row[5] or row[6]:
        raise ValueError("DEPLOYMENT_RUNTIME_PRINCIPAL_PRIVILEGES")
    _reject_privilege_drift(connection)
    return {"name": row[0], "oid": row[2]}
