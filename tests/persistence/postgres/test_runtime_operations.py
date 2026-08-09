from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_runtime_configuration,
    publish_controlled_trading_calendar,
)
from market_regime_alpha.application.runtime_operations.observability import (
    PostgresRuntimeObservability,
)
from market_regime_alpha.application.runtime_operations.preflight import (
    CanonicalRuntimePreflight,
    PreflightStatus,
    RuntimePreflightRequest,
)
from market_regime_alpha.application.runtime_operations.query import (
    CanonicalDagNodeStatus,
    CanonicalDagNodeType,
    PostgresCanonicalRuntimeQuery,
)
from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data.providers.public_composite import (
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from tests.persistence.postgres.test_free_data_continuous_runtime import (
    _calendar,
    _configuration,
    _continuous_command,
    _tick,
)


def test_preflight_reads_real_postgres_and_blocks_missing_champions(
    tmp_path: Path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _calendar()
    configuration = _configuration(calendar)
    calendar_path = publish_controlled_trading_calendar(
        root=tmp_path / "calendars", artifact=calendar
    )
    configuration_path = publish_controlled_runtime_configuration(
        root=tmp_path / "configurations", artifact=configuration
    )
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    command = _continuous_command(
        ("000001.SZ",),
        calendar,
        configuration,
        RuntimeAuthorityMode.RESEARCH,
    )
    journal = PostgresContinuousResearchJournal(postgres_factory)
    journal.create_or_get(command)
    policy = canonical_free_operational_evidence_policy()

    report = CanonicalRuntimePreflight(postgres_factory).inspect(
        RuntimePreflightRequest(
            trading_date=command.trading_date,
            runtime_mode=command.authority_mode,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            operational_policy_effective_from=min(
                item.effective_from for item in policy.themes
            ),
            artifact_root=artifact_root,
            runtime_configuration_path=configuration_path,
            trading_calendar_path=calendar_path,
            run_id=command.run_id,
            minimum_free_bytes=1,
            maximum_clock_skew=timedelta(seconds=10),
        )
    )

    checks = {item.check_name: item for item in report.checks}
    assert report.status is PreflightStatus.BLOCKED
    assert checks["POSTGRESQL_CONNECTIVITY"].status is PreflightStatus.READY
    assert checks["MIGRATION_CONSISTENCY"].status is PreflightStatus.READY
    assert checks["RUNTIME_SCHEMA"].status is PreflightStatus.READY
    assert checks["MODEL_GOVERNANCE"].reason_codes == (
        "CHAMPION_AUTHORITY_MISSING",
    )
    assert checks["RUNTIME_RECOVERY"].status is PreflightStatus.READY
    assert report.grants_trading_authority is False


def test_query_and_observability_explain_failed_tick_without_recomputation(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    calendar = _calendar()
    configuration = _configuration(calendar)
    command = _continuous_command(
        ("000001.SZ",),
        calendar,
        configuration,
        RuntimeAuthorityMode.RESEARCH,
    )
    now = datetime.now(UTC).replace(microsecond=0)
    journal = PostgresContinuousResearchJournal(
        postgres_factory,
        clock=lambda: now,
    )
    journal.create_or_get(command)
    tick_command = _tick(command, "runtime-operations")
    journal.admit_tick(
        tick_command,
        session_phase=ContinuousSessionPhase.DECISION_WINDOW,
    )
    claim = journal.claim_tick(
        run_id=command.run_id,
        tick_id=tick_command.tick_id,
    )
    journal.fail_tick(
        claim=claim,
        error="RECORDED_PROVIDER_OUTAGE",
        retryable=False,
        retry_at=None,
    )

    query = PostgresCanonicalRuntimeQuery(
        postgres_factory, clock=lambda: now
    )
    inspection = query.inspect_run(command.run_id)
    tick_nodes = inspection.nodes_of_type(CanonicalDagNodeType.TICK)
    assert len(tick_nodes) == 1
    assert tick_nodes[0].status is CanonicalDagNodeStatus.FAILED
    assert inspection.nodes_of_type(CanonicalDagNodeType.SUMMARY) == ()
    assert inspection.read_only is True
    tick_projection = query.inspect_tick(command.run_id, tick_command.tick_id)
    assert tick_projection["decision_recomputed"] is False

    observability = PostgresRuntimeObservability(
        postgres_factory, clock=lambda: now
    )
    trace = observability.trace_run(command.run_id)
    assert trace["decision_input"] is False
    assert trace["observations"][0]["status"] == "FAILED"
    assert trace["observations"][0]["fencing_token"] == claim.fencing_token
    metrics = observability.metrics(command.run_id)
    assert metrics["tick_failure_count"] == 1
    assert metrics["provider_failures"] == 0
