from uuid import uuid4
from datetime import timedelta
from datetime import datetime, UTC

import pytest
from psycopg.conninfo import conninfo_to_dict

from market_regime_alpha.infrastructure.postgres.evidence_backup import _table_hashes
from market_regime_alpha.infrastructure.postgres.queries.prospective_health import PostgresProspectiveHealthReadPort
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.application import ActorType, CommandContext
from tests.contracts.market import prospective_health_fixture


@pytest.fixture
def canonical_prospective_stack(target_database_url, tmp_path, request):
    yield from prospective_health_fixture.canonical_prospective_stack.__wrapped__(target_database_url, tmp_path, request)


def test_health_has_exact_expected_roster_and_zero_business_writes(canonical_prospective_stack):
    fixture = canonical_prospective_stack
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    result = PostgresProspectiveHealthReadPort(fixture.pool).inspect("health_fixture")
    assert result["database"]["name"] == conninfo_to_dict(fixture.settings.database_url)["dbname"]
    assert result["database"]["oid"] > 0
    assert result["owner_reconciliation"] == "NOT_PERFORMED"
    assert len(result["generations"]) == 1
    assert len(result["slices"]) == 9
    assert result["summary"]["counts"]["expected"] == 9
    assert result["summary"]["counts"]["future"] == 9
    assert result["summary"]["operational_state"] == "NOT_DUE"
    assert result["summary"]["alerts"] == ()
    assert result["summary"]["rates"]["capture_success"]["state"] == "NOT_ESTIMABLE"
    assert all(s["runtime_step_id"] is not None for s in result["slices"])
    scoped = PostgresProspectiveHealthReadPort(fixture.pool).inspect(
        "health_fixture", cutover_at=result["observed_at"], recent_sessions=3
    )
    assert scoped["scopes"]["ALL_HISTORY"]["summary"] == result["summary"]
    assert scoped["scopes"]["POST_CURRENT_CUTOVER"]["summary"]["counts"]["expected"] == 9
    assert scoped["scopes"]["LAST_N_TRADING_SESSIONS"]["requested_sessions"] == 3
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before


def test_health_rejects_unknown_series_and_roster_budget(canonical_prospective_stack):
    port = PostgresProspectiveHealthReadPort(canonical_prospective_stack.pool)
    with pytest.raises(ValueError, match="series"):
        port.inspect(str(uuid4()))
    with pytest.raises(ValueError, match="budget"):
        port.inspect("health_fixture", maximum_slices=8)


def test_scopes_use_scheduled_session_and_window_not_generation_creation(canonical_prospective_stack, monkeypatch):
    port = PostgresProspectiveHealthReadPort(canonical_prospective_stack.pool)
    project = port._project
    # Only the read projection clock is frozen. No operational clock or fact is
    # changed; the real canonical fixture has four windows on each of two days.
    def projected(*args, **kwargs):
        schedules = args[6]
        second = next(s['trading_session_id'] for s in schedules if s['schedule_slot']=='OUTCOME_POST_CLOSE')
        kwargs.update(cutover_at=datetime(2099,1,6,tzinfo=UTC),
                      recent=[{'session_id':second,'session_date':'2099-01-06'}],recent_sessions=1)
        return project(args[0], datetime(2099,1,6,16,tzinfo=UTC), *args[2:], **kwargs)
    monkeypatch.setattr(port,'_project',projected)
    result=port.inspect('health_fixture')
    scopes=result['scopes']
    assert scopes['ALL_HISTORY']['summary']['counts']['expected']==9
    assert scopes['ALL_HISTORY']['summary']['counts']['opened_expected']==8
    assert scopes['POST_CURRENT_CUTOVER']['summary']['counts']['expected']==5
    assert scopes['POST_CURRENT_CUTOVER']['summary']['counts']['opened_expected']==4
    assert scopes['LAST_N_TRADING_SESSIONS']['summary']['counts']['expected']==4
    assert scopes['LAST_N_TRADING_SESSIONS']['summary']['counts']['opened_expected']==4
    assert scopes['POST_CURRENT_CUTOVER']['summary']['rates']['capture_success']['denominator']==4


@pytest.mark.parametrize("damage", ("schedule", "root", "member", "runtime"))
def test_health_rejects_corrupted_full_roster_without_writing_facts(canonical_prospective_stack, damage):
    fixture = canonical_prospective_stack
    # Explicit disposable target_database_url only; all trigger guards restored.
    with fixture.pool.connection() as connection:
        if damage == "schedule":
            connection.execute("ALTER TABLE mra.prospective_archive_slice_schedule DISABLE TRIGGER ALL")
            connection.execute("DELETE FROM mra.prospective_archive_slice_schedule WHERE ordinal=9")
            connection.execute("ALTER TABLE mra.prospective_archive_slice_schedule ENABLE TRIGGER ALL")
        elif damage == "root":
            connection.execute("ALTER TABLE mra.market_archive DISABLE TRIGGER ALL")
            connection.execute("UPDATE mra.market_archive SET content_sha256=%s", ("4"*64,))
            connection.execute("ALTER TABLE mra.market_archive ENABLE TRIGGER ALL")
        elif damage == "member":
            connection.execute("ALTER TABLE mra.prospective_archive_generation_member DISABLE TRIGGER ALL")
            connection.execute("UPDATE mra.prospective_archive_generation_member SET content_sha256=%s", ("5"*64,))
            connection.execute("ALTER TABLE mra.prospective_archive_generation_member ENABLE TRIGGER ALL")
        else:
            connection.execute("ALTER TABLE mra.runtime_run DISABLE TRIGGER ALL")
            connection.execute("UPDATE mra.runtime_run SET config_hash=%s WHERE fire_key LIKE %s", ("6"*64, "%:capture:%"))
            connection.execute("ALTER TABLE mra.runtime_run ENABLE TRIGGER ALL")
        connection.commit()
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    with pytest.raises(ArtifactIntegrityError, match="root/roster"):
        PostgresProspectiveHealthReadPort(fixture.pool).inspect("health_fixture")
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before


def test_health_projects_runtime_unknown_effect_and_expired_lease(canonical_prospective_stack):
    fixture = canonical_prospective_stack
    runtime = fixture.application.runtime
    def context(key):
        return CommandContext(key, ActorType.OPERATOR, "health-test", "HEALTH_TEST")
    claim = runtime.claim_next(
        run_id=fixture.registration.capture_run_ids[0], worker_id="health-test",
        lease_duration=timedelta(minutes=1), context=context("health-claim"),
    )
    assert claim is not None
    runtime.start_attempt(claim, context=context("health-start"))
    runtime.fail_attempt(claim, error_class="INTEGRITY", error_code="EXTERNAL_EFFECT_UNKNOWN", context=context("health-fail"))
    other = runtime.claim_next(
        run_id=fixture.registration.capture_run_ids[1], worker_id="health-test",
        lease_duration=timedelta(milliseconds=1), context=context("health-other-claim"),
    )
    assert other is not None
    # This declared millisecond lease expires during the complete table scan;
    # there is no wait, clock mutation or Provider effect in this fixture.
    with fixture.pool.connection(read_only=True) as connection:
        before = _table_hashes(connection)
    result = PostgresProspectiveHealthReadPort(fixture.pool).inspect("health_fixture")
    assert result["summary"]["counts"]["unknown_external_effect"] == 1
    assert result["summary"]["counts"]["expired_active_lease"] == 1
    assert result["summary"]["counts"]["successful_capture"] == 0
    assert result["summary"]["rates"]["capture_success"]["state"] == "NOT_ESTIMABLE"
    ids = {a["attempt_id"] for s in result["slices"] for a in s["attempts"]}
    assert ids == {claim.attempt_id, other.attempt_id}
    with fixture.pool.connection(read_only=True) as connection:
        assert _table_hashes(connection) == before
