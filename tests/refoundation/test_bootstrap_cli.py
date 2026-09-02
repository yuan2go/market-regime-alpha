from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.bootstrap import (
    TargetSettings,
    bootstrap_application,
)
from market_regime_alpha.decision_support.application import (
    ContextCommands,
    DecisionRunVerifier,
    DecisionSupportApplication,
    InferenceCommands,
    OpportunityCommands,
    PortfolioCommands,
    RiskCommands,
    StrategyCommands,
)
from market_regime_alpha.infrastructure.postgres.schema import (
    SchemaManager,
    SchemaMissingError,
)
from market_regime_alpha.infrastructure.postgres.queries import (
    PostgresCandidateQueryProvider,
)
from market_regime_alpha.interfaces.cli import main
from market_regime_alpha.market.application import (
    ArchiveCommands,
    MarketArchiveOperations,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.research_qualification.application import (
    EvaluationCommands,
    ExperimentCommands,
    ResearchPartitionCommands,
    ResearchEvaluationVerifier,
)
from market_regime_alpha.selection.application import (
    CandidateApplication,
    SelectionApplication,
)
from market_regime_alpha.runtime.domain import (
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)


def _environment(database_url: str, artifact_root: str) -> dict[str, str]:
    return {
        "MRA_DATABASE_URL": database_url,
        "MRA_ARTIFACT_ROOT": artifact_root,
        "MRA_SCHEMA": "mra",
        "MRA_SCHEMA_EPOCH": "MRA_REFOUNDATION_1",
        "MRA_POOL_MIN_SIZE": "0",
        "MRA_POOL_MAX_SIZE": "4",
    }


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="cli-test",
        reason_code="CLI_SMOKE",
    )


def test_target_settings_reject_unknown_prefixed_keys(
    target_database_url: str,
    tmp_path,
) -> None:
    environment = _environment(target_database_url, str(tmp_path / "artifacts"))
    environment["MRA_UNDECLARED_SWITCH"] = "true"

    with pytest.raises(ValueError, match="unknown MRA configuration keys"):
        TargetSettings.from_environ(environment)


def test_normal_application_startup_fails_closed_without_schema_or_ddl(
    target_database_url: str,
    tmp_path,
) -> None:
    settings = TargetSettings.from_environ(_environment(target_database_url, str(tmp_path / "artifacts")))

    with pytest.raises(SchemaMissingError, match="SCHEMA_MISSING"):
        bootstrap_application(settings)

    with psycopg.connect(target_database_url) as connection:
        assert connection.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mra')").fetchone() == (False,)


def test_mra_db_bootstrap_verify_and_runtime_inspection_smoke(
    target_database_url: str,
    tmp_path,
) -> None:
    environment = _environment(target_database_url, str(tmp_path / "artifacts"))
    bootstrap_output = StringIO()
    verify_output = StringIO()

    assert (
        main(
            ["db", "bootstrap"],
            environ=environment,
            stdout=bootstrap_output,
            stderr=StringIO(),
        )
        == 0
    )
    assert (
        main(
            ["db", "verify"],
            environ=environment,
            stdout=verify_output,
            stderr=StringIO(),
        )
        == 0
    )
    assert json.loads(bootstrap_output.getvalue())["created"] is True
    assert json.loads(verify_output.getvalue())["epoch"] == "MRA_REFOUNDATION_1"

    application = bootstrap_application(TargetSettings.from_environ(environment))
    try:
        assert isinstance(application.selection, SelectionApplication)
        assert isinstance(application.candidates, CandidateApplication)
        assert isinstance(application.decision_support, DecisionSupportApplication)
        assert isinstance(application.decision_contexts, ContextCommands)
        assert isinstance(application.decision_strategies, StrategyCommands)
        assert isinstance(application.decision_inference, InferenceCommands)
        assert isinstance(application.decision_opportunities, OpportunityCommands)
        assert isinstance(application.decision_portfolios, PortfolioCommands)
        assert isinstance(application.decision_risk, RiskCommands)
        assert isinstance(application.decision_support_verifier, DecisionRunVerifier)
        assert isinstance(application.research_partitions, ResearchPartitionCommands)
        assert isinstance(application.research_experiments, ExperimentCommands)
        assert isinstance(application.research_evaluations, EvaluationCommands)
        assert isinstance(application.market_archives, ArchiveCommands)
        assert isinstance(application.archive_operations, MarketArchiveOperations)
        assert isinstance(
            application.research_evaluation_verifier,
            ResearchEvaluationVerifier,
        )
        assert isinstance(
            application.candidate_queries,
            PostgresCandidateQueryProvider,
        )
        schedule = ScheduleSpec(
            schedule_id=uuid4(),
            schedule_code="cli-smoke",
            revision=1,
            runtime_mode=RuntimeMode.OPERATIONAL,
            schedule_expression=None,
            timezone_name="Asia/Shanghai",
            step_catalog_hash="a" * 64,
            enabled=True,
        )
        application.runtime.create_schedule(schedule, _context("schedule"))
        config = application.artifacts.publish(
            b'{"cli":"smoke"}',
            media_type="application/json",
            context=_context("config"),
        )
        run = RunSpec(
            run_id=uuid4(),
            schedule_id=schedule.schedule_id,
            fire_key="manual-1",
            runtime_mode=RuntimeMode.OPERATIONAL,
            requested_at=datetime.now(timezone.utc),
            decision_time=None,
            code_sha="1" * 40,
            config_artifact_id=config.artifact_id,
            config_hash=config.content_sha256,
        )
        application.runtime.schedule_run(
            run,
            (
                StepSpec(
                    step_key="capture",
                    step_kind="CAPTURE",
                    implementation="tests.capture",
                    implementation_version="1",
                    ordinal=1,
                    required=True,
                    request_hash="c" * 64,
                    input_evidence_hash=None,
                    retry_policy=RetryPolicy(
                        max_attempts=1,
                        backoff=(),
                        retryable_codes=frozenset(),
                    ),
                ),
            ),
            (),
            _context("run"),
        )
        application.runtime.start_run(run.run_id, _context("start"))
    finally:
        application.close()

    inspect_output = StringIO()
    assert (
        main(
            ["runtime", "inspect", "--run-id", str(run.run_id)],
            environ=environment,
            stdout=inspect_output,
            stderr=StringIO(),
        )
        == 0
    )
    payload = json.loads(inspect_output.getvalue())
    assert payload["run_id"] == str(run.run_id)
    assert payload["run_state"] == "RUNNING"
    assert payload["steps"][0]["state"] == "READY"


def test_mra_cli_missing_schema_returns_nonzero_without_bootstrap(
    target_database_url: str,
    tmp_path,
) -> None:
    error_output = StringIO()
    code = main(
        ["runtime", "inspect", "--run-id", str(uuid4())],
        environ=_environment(target_database_url, str(tmp_path / "artifacts")),
        stdout=StringIO(),
        stderr=error_output,
    )

    assert code != 0
    assert "SCHEMA_MISSING" in error_output.getvalue()
    with psycopg.connect(target_database_url) as connection:
        assert connection.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mra')").fetchone() == (False,)


def test_mra_cli_recreate_plan_apply_requires_same_operator_and_exact_plan(
    target_database_url: str,
    tmp_path,
) -> None:
    environment = _environment(target_database_url, str(tmp_path / "artifacts"))
    manager = SchemaManager(target_database_url)
    manager.bootstrap()
    identity = manager.database_identity()
    plan_path = tmp_path / "recreate-plan.json"
    plan_output = StringIO()

    assert (
        main(
            [
                "db",
                "recreate-plan",
                "--expected-database-name",
                identity.database_name,
                "--expected-database-oid",
                str(identity.database_oid),
                "--operator-id",
                "cli-operator",
                "--reason",
                "exercise explicit draft recreate",
                "--backup-attestation",
                "isolated disposable test database",
                "--output",
                str(plan_path),
            ],
            environ=environment,
            stdout=plan_output,
            stderr=StringIO(),
        )
        == 0
    )
    plan_payload = json.loads(plan_output.getvalue())
    assert plan_path.exists()
    assert plan_payload["active_connection_pids"] == []

    wrong_operator_error = StringIO()
    assert (
        main(
            [
                "db",
                "recreate-apply",
                "--plan",
                str(plan_path),
                "--challenge",
                plan_payload["challenge"],
                "--operator-id",
                "different-operator",
            ],
            environ=environment,
            stdout=StringIO(),
            stderr=wrong_operator_error,
        )
        == 2
    )
    assert "RECREATE_OPERATOR_MISMATCH" in wrong_operator_error.getvalue()
    assert manager.verify().epoch == "MRA_REFOUNDATION_1"

    apply_output = StringIO()
    assert (
        main(
            [
                "db",
                "recreate-apply",
                "--plan",
                str(plan_path),
                "--challenge",
                plan_payload["challenge"],
                "--operator-id",
                "cli-operator",
            ],
            environ=environment,
            stdout=apply_output,
            stderr=StringIO(),
        )
        == 0
    )
    result = json.loads(apply_output.getvalue())
    assert result["removed_application_schema"] == "mra"
    assert result["verification"]["created"] is True


def test_mra_cli_rejects_malformed_recreate_plan_without_traceback(
    target_database_url: str,
    tmp_path,
) -> None:
    environment = _environment(target_database_url, str(tmp_path / "artifacts"))
    plan_path = tmp_path / "malformed-plan.json"
    plan_path.write_text('{"database_name":"incomplete"}', encoding="utf-8")
    error = StringIO()

    assert (
        main(
            [
                "db",
                "recreate-apply",
                "--plan",
                str(plan_path),
                "--challenge",
                "0" * 24,
                "--operator-id",
                "cli-operator",
            ],
            environ=environment,
            stdout=StringIO(),
            stderr=error,
        )
        == 2
    )
    assert "required shape" in error.getvalue()
