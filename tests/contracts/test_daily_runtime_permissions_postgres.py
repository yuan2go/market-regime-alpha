"""Full daily owner commands authenticate as a restricted login; fixture setup stays separate."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations
from tests.contracts.research_qualification.test_daily_vertical_postgres import (
    test_completed_model_is_consumed_without_backtest_and_publication_is_replayable as vertical,
)

WRITE_TABLES = (
    "evaluation_observation",
    "research_partition_outcome_access",
    "decision_run_research_qualification_roster",
    "decision_run_research_qualification_member",
    "artifact",
    "artifact_gc_candidate",
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


def test_restricted_runtime_login_completes_prediction_maturity_recovery_and_replay(
    target_database_url, tmp_path, monkeypatch, record_property
):
    role = "daily_runtime_" + uuid4().hex
    password = uuid4().hex
    active = ContextVar("restricted_daily_command", default=False)
    with psycopg.connect(target_database_url) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
    runtime_pool = TargetPostgresPool(make_conninfo(target_database_url, user=role, password=password))
    original_connection = TargetPostgresPool.connection
    initialized = False

    @contextmanager
    def restricted_connection(pool, *, read_only=False):
        nonlocal initialized
        if active.get() and pool is not runtime_pool:
            if not initialized:
                with psycopg.connect(target_database_url) as admin:
                    admin.execute(sql.SQL("GRANT USAGE ON SCHEMA mra TO {}").format(sql.Identifier(role)))
                    admin.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA mra TO {}").format(sql.Identifier(role)))
                    for table in WRITE_TABLES:
                        admin.execute(sql.SQL("GRANT INSERT, UPDATE ON mra.{} TO {}").format(sql.Identifier(table), sql.Identifier(role)))
                    for table, column in REFERENCE_LOCKS.items():
                        admin.execute(
                            sql.SQL("GRANT UPDATE({}) ON mra.{} TO {}").format(
                                sql.Identifier(column), sql.Identifier(table), sql.Identifier(role)
                            )
                        )
                initialized = True
            with original_connection(runtime_pool, read_only=read_only) as connection:
                assert connection.info.user == role
                yield connection
        else:
            with original_connection(pool, read_only=read_only) as connection:
                yield connection

    def wrap(function):
        @wraps(function)
        def under_login(*args, **kwargs):
            token = active.set(True)
            try:
                return function(*args, **kwargs)
            finally:
                active.reset(token)

        return under_login

    try:
        with monkeypatch.context() as patch:
            patch.setattr(TargetPostgresPool, "connection", restricted_connection)
            for name in (
                "execute",
                "execute_step",
                "settle_and_evaluate",
                "_execute_outcome_step",
                "abstain",
                "report",
                "replay",
                "replay_completed_cycle",
                "record_research_disposition",
            ):
                patch.setattr(DailyResearchOperations, name, wrap(getattr(DailyResearchOperations, name)))
            vertical(target_database_url, tmp_path, False, True, patch, record_property)
        with original_connection(runtime_pool, read_only=True) as c:
            assert c.execute(
                "SELECT has_table_privilege('mra.model_version','INSERT'),has_table_privilege('mra.schema_migrations','INSERT'),has_table_privilege('mra.provider_qualification_decision','INSERT')"
            ).fetchone() == (False, False, False)
    finally:
        runtime_pool.close()
        with psycopg.connect(target_database_url) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
