"""Canonical fixture with declared synthetic 2099 sessions, never live evidence."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.market.application import ProspectiveArchiveInstrument, build_target_aligned_prospective_manifest
from market_regime_alpha.market.domain import InstrumentIdentifier, NormalizationBatch, ProspectiveArchiveSession, TradingSession, derive_target_archive_sessions
from market_regime_alpha.market.ports import CaptureRequest
from tests.contracts.decision_support.test_decision_postgres import _register_target
from tests.contracts.research_qualification import test_research_postgres as research


@pytest.fixture
def canonical_prospective_stack(target_database_url, tmp_path, request):
    stack = research.dataset_stack.__wrapped__(target_database_url, tmp_path, request)
    target = _register_target(stack)
    capture = stack.market.capture(
        CaptureRequest(stack.product.provider_product_id, "prospective-calendar", "fixture://declared-2099-calendar", "1" * 64),
        research._BytesProvider(), research._context("health-calendar-capture", "HEALTH_FIXTURE"),
    ).capture
    sessions = tuple(TradingSession(
        session_id=uuid4(), exchange="XSHG", session_date=day, timezone_name="Asia/Shanghai",
        open_at=datetime.combine(day, time(1, 30), UTC),
        break_start_at=datetime.combine(day, time(3, 30), UTC),
        break_end_at=datetime.combine(day, time(5), UTC),
        close_at=datetime.combine(day, time(7), UTC),
        decision_reference_at=datetime.combine(day, time(6, 55), UTC),
        source_capture_id=capture.capture_id,
    ) for day in (date(2099, 1, 5), date(2099, 1, 6), date(2099, 1, 7)))
    identifier = InstrumentIdentifier(
        instrument_identifier_id=uuid4(), instrument_id=stack.instrument_id,
        identifier_scheme="BAOSTOCK", identifier_value="sh.600000",
        effective_from=datetime(2098, 1, 1, tzinfo=UTC), effective_to=None,
        revision=1, supersedes_identifier_id=None, source_capture_id=capture.capture_id,
    )
    stack.market.normalize(capture.capture_id, research._Normalizer(lambda source: NormalizationBatch(
        source_capture_id=source.capture_id, source_provider_product_id=source.provider_product_id,
        trading_sessions=sessions, instrument_identifiers=(identifier,),
    )), research._context("health-calendar-normalize", "HEALTH_FIXTURE"))
    settings = TargetSettings(target_database_url, tmp_path / "research-dataset-artifacts")
    with bootstrap_application(settings) as app:
        contract = app.target_archive_schedules.exact_contract(target.target_definition_id)
        resolved = derive_target_archive_sessions(
            exchange="XSHG", decision_session_id=sessions[0].session_id.value,
            sessions=tuple(ProspectiveArchiveSession(s.session_id.value, s.exchange, s.session_date, s.open_at, s.close_at) for s in sessions),
            checkpoints=contract.checkpoints, later_verification_session_offset=2,
        )
        with stack.pool.connection(read_only=True) as connection:
            now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        manifest = build_target_aligned_prospective_manifest(
            provider_product_id=stack.product.provider_product_id,
            code_artifact_id=target.algorithm.code_artifact.artifact_id,
            config_artifact_id=target.algorithm.config_artifact.artifact_id,
            contract=contract, resolved_sessions=resolved,
            instruments=(ProspectiveArchiveInstrument(stack.instrument_id.value, identifier.instrument_identifier_id, "sh.600000"),),
            series_code="health_fixture", generation=1, predecessor_market_archive_id=None,
            planned_not_before=now, provenance_sha256="a" * 64,
        )
        stop_after_archive = getattr(request, "param", None) == "interrupt_capture_registration"
        boundary_count = 0
        def before_action():
            nonlocal boundary_count
            boundary_count += 1
            if stop_after_archive and boundary_count == 4:
                raise InterruptedError("fixture process interruption after Archive commit")
        try:
            registration = app.prospective_archives.predeclare(
                manifest, code_sha="1" * 40, actor_id="health-fixture", lease_duration=timedelta(seconds=60),
                before_action=before_action,
            )
        except InterruptedError:
            if not stop_after_archive:
                raise
            registration = None
        yield SimpleNamespace(stack=stack, application=app, pool=stack.pool,
                              manifest=manifest, registration=registration, settings=settings)
