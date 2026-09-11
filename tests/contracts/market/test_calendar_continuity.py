"""Explicit calendar bytes, coverage closure, and bounded Runtime behavior."""

from dataclasses import asdict, replace
from datetime import date, timedelta
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.queries.calendar_continuity import verify_calendar_coverage
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer
from market_regime_alpha.infrastructure.providers.baostock_calendar_normalizer import BaoStockCalendarNormalizer, decode_calendar_response
from market_regime_alpha.interfaces.calendar_continuity import CalendarRefreshPlan, calendar_steps, refresh_calendar
from market_regime_alpha.market.domain import GapFactKind
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.market.test_baostock_archive_normalizer import _capture, _payload


def _query():
    return BaoStockArchiveQuery(BaoStockArchiveQueryKind.TRADE_DATES, date(2026, 9, 3), date(2026, 9, 5))


def _bytes(rows=None):
    return _payload(_query(), ["calendar_date", "is_trading_day"], rows if rows is not None else [["2026-09-03", "1"], ["2026-09-04", "0"], ["2026-09-05", "1"]])


def test_explicit_saturday_open_and_weekday_closed_are_provider_observations():
    capture = _capture()
    batch = BaoStockCalendarNormalizer(_query()).normalize(capture, _bytes())
    assert [session.session_date for session in batch.trading_sessions] == [date(2026, 9, 3), date(2026, 9, 5)]
    assert {session.exchange for session in batch.trading_sessions} == {"XSHG"}
    assert batch.gaps == ()
    assert BaoStockCalendarNormalizer(_query()).normalize(capture, _bytes()) == batch


@pytest.mark.parametrize("rows", [[], [["2026-09-03", "1"]]])
def test_absent_future_civil_date_is_exact_gap_without_invented_event_time(rows):
    capture = _capture()
    batch = BaoStockCalendarNormalizer(_query()).normalize(capture, _bytes(rows))
    assert len(batch.gaps) == 3 - len(rows)
    assert all(gap.fact_kind is GapFactKind.TRADING_SESSION and gap.exchange == "XSHG" and gap.session_date is not None
        and gap.event_start is None and gap.event_end is None and gap.session_id is None for gap in batch.gaps)


@pytest.mark.parametrize("rows", [
    [["2026-09-03", "2"]], [["2026-09-03", 1]], [["2026-09-03", "1"], ["2026-09-03", "1"]],
    [["2026-09-02", "1"]], [["2026-09-06", "0"]], [["2026-9-3", "1"]],
])
def test_calendar_invalid_status_duplicate_or_out_of_request_fails(rows):
    with pytest.raises(ValueError):
        BaoStockCalendarNormalizer(_query()).normalize(_capture(), _bytes(rows))


def test_exact_request_binding_and_empty_closed_window_fail_closed():
    with pytest.raises(ValueError, match="IDENTITY"):
        BaoStockCalendarNormalizer(replace(_query(), end_date=date(2026, 9, 6))).normalize(_capture(), _bytes())
    with pytest.raises(ValueError, match="NO_OPEN_SESSIONS"):
        BaoStockCalendarNormalizer(_query()).normalize(_capture(), _bytes([[str(date(2026, 9, day)), "0"] for day in (3, 4, 5)]))
    query = replace(_query(), end_date=_query().start_date + timedelta(days=120))
    with pytest.raises(ValueError, match="IDENTITY"):
        decode_calendar_response(_payload(query, ["calendar_date", "is_trading_day"], []))


def _witness(legacy=False, missing=False):
    capture = _capture()
    content = _bytes([["2026-09-03", "1"]] if missing else None)
    normalizer = BaoStockArchiveNormalizer(_query()) if legacy else BaoStockCalendarNormalizer(_query())
    batch = normalizer.normalize(capture, content)
    sessions = [{**asdict(item), "session_id": item.session_id.value} for item in batch.trading_sessions]
    receipt = uuid4()
    roster = tuple({"reference_id": item["session_id"], "reference_kind": "TRADING_SESSION"} for item in sorted(sessions, key=lambda item: str(item["session_id"])))
    roster_hash = canonical_json_sha256(roster)
    request = CaptureRequest(capture.provider_product_id, capture.capture_key, _query().resource, canonical_json_sha256({"headers": {}}))
    known = capture.temporal.known_at.value
    row = {"capture_id": capture.capture_id, "provider_product_id": capture.provider_product_id, "capture_key": capture.capture_key,
        "size_bytes": len(content), "artifact_sha256": sha256(content).hexdigest(), "request_hash": canonical_json_sha256(request),
        "normalization_request_hash": canonical_json_sha256({"capture_id": capture.capture_id, "normalizer_contract": normalizer.contract}),
        "receipt_status": "SUCCEEDED", "command_kind": "NORMALIZE_MARKET_PIT", "scope_id": str(capture.capture_id),
        "result_aggregate_kind": "MARKET_NORMALIZATION", "result_aggregate_id": str(capture.capture_id), "result_aggregate_version": 1,
        "capture_started_at": known, "capture_completed_at": known, "known_at": known, "normalized_at": known,
        "reference_count": len(roster), "reference_roster_sha256": roster_hash, "normalization_receipt_id": receipt,
        "normalization_sha256": canonical_json_sha256({"capture_id": capture.capture_id, "normalization_receipt_id": receipt,
            "reference_count": len(roster), "reference_roster_sha256": roster_hash}), "source_gap_count": len(batch.gaps)}
    return row, sessions, content, known


@pytest.mark.parametrize("legacy", [False, True])
def test_full_physical_bytes_and_exact_owner_roster_prove_coverage(legacy):
    row, sessions, content, known = _witness(legacy)
    result = verify_calendar_coverage(row, sessions, content, known)
    assert result["state"] == "VERIFIED"
    assert len(result["session_ids"]) == 2
    assert result["coverage_through"] == date(2026, 9, 5)
    assert result["business_writes"] == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_partial_response_never_becomes_coverage_even_if_legacy_normalized(legacy):
    row, sessions, content, known = _witness(legacy, missing=True)
    assert verify_calendar_coverage(row, sessions, content, known)["state"] == "SOURCE_GAP"


@pytest.mark.parametrize("mutation", ["bytes", "request", "normalizer", "receipt", "time", "roster", "clock", "hash"])
def test_coverage_tampering_fails_closed(mutation):
    row, sessions, content, known = _witness()
    if mutation == "bytes":
        content += b" "
    elif mutation == "request":
        row["request_hash"] = "0" * 64
    elif mutation == "normalizer":
        row["normalization_request_hash"] = "0" * 64
    elif mutation == "receipt":
        row["receipt_status"] = "PENDING"
    elif mutation == "time":
        row["normalized_at"] = known + timedelta(seconds=1)
    elif mutation == "roster":
        sessions.pop()
    elif mutation == "clock":
        sessions[0]["close_at"] += timedelta(minutes=1)
    else:
        row["reference_roster_sha256"] = "0" * 64
    with pytest.raises(ArtifactIntegrityError):
        verify_calendar_coverage(row, sessions, content, known)


def test_calendar_plan_is_once_per_actual_civil_day_and_capture_has_one_attempt():
    capture = _capture()
    first = CalendarRefreshPlan(capture.provider_product_id, capture.temporal.known_at.value, date(2026, 9, 5), "a" * 40)
    second = replace(first, requested_at=first.requested_at + timedelta(minutes=1))
    assert first.identity == second.identity and first.run_id == second.run_id
    assert first.content_sha256 != second.content_sha256
    assert CalendarRefreshPlan.decode(first.content) == first
    value = json.loads(first.content)
    value["query"]["end_date"] = "2026-09-06"
    with pytest.raises(ArtifactIntegrityError, match="BYTES_DIFFER"):
        CalendarRefreshPlan.decode(json.dumps(value).encode())
    steps, dependencies = calendar_steps(first)
    assert steps[0].retry_policy.max_attempts == 1
    assert steps[0].external_effect_class.value == "CONTENT_PUT"
    assert steps[1].external_effect_class.value == "NONE"
    assert len(dependencies) == 1


def test_unknown_previous_date_blocks_without_provider_or_new_run():
    capture = _capture()
    app = SimpleNamespace(daily_prediction_reads=SimpleNamespace(now=lambda: capture.temporal.known_at.value),
        calendar_continuity_reads=SimpleNamespace(unresolved_work=lambda _: [{"attempt_state": "RECONCILIATION_REQUIRED"}]))
    result = refresh_calendar(app, provider_product_id=capture.provider_product_id, code_sha="a" * 40,
        provider=None, worker_id="calendar", before_action=lambda: None)
    assert result["state"] == "BLOCKED"
    assert result["reason_code"] == "CALENDAR_ATTEMPT_REQUIRES_RECONCILIATION"


def test_verified_horizon_clipped_by_current_use_needs_no_new_provider_effect():
    row, sessions, content, known = _witness()
    coverage = verify_calendar_coverage(row, sessions, content, known)
    app = SimpleNamespace(daily_prediction_reads=SimpleNamespace(now=lambda: known),
        calendar_continuity_reads=SimpleNamespace(unresolved_work=lambda _: [], calendar_coverage=lambda *_: coverage))
    result = refresh_calendar(app, provider_product_id=row["provider_product_id"], code_sha="a" * 40, provider=None,
        worker_id="calendar", before_action=lambda: None, expires_at=known + timedelta(days=2))
    assert result["state"] == "NOT_DUE"


@pytest.mark.parametrize("state", ["FAILED", "WAITING", "SUCCEEDED"])
def test_same_day_terminal_run_is_never_reopened(monkeypatch, state):
    import market_regime_alpha.interfaces.calendar_continuity as module
    capture = _capture()
    known = capture.temporal.known_at.value
    plan = CalendarRefreshPlan(capture.provider_product_id, known, date(2026, 9, 5), "a" * 40)
    monkeypatch.setattr(module, "_verify_run", lambda *_: None)
    app = SimpleNamespace(daily_prediction_reads=SimpleNamespace(now=lambda: known, run_plan_content=lambda _: plan.content),
        calendar_continuity_reads=SimpleNamespace(unresolved_work=lambda _: [], calendar_coverage=lambda *_: {"state": "UNAVAILABLE"}),
        runtime=SimpleNamespace(inspect_run=lambda _: SimpleNamespace(run_state=state)))
    result = refresh_calendar(app, provider_product_id=capture.provider_product_id, code_sha="a" * 40, provider=None,
        worker_id="calendar", before_action=lambda: None)
    assert result["reason_code"] == ("CALENDAR_COVERAGE_UNAVAILABLE" if state == "SUCCEEDED" else "CALENDAR_RUN_" + state)


@pytest.mark.parametrize("state", ["SOURCE_GAP", "UNAVAILABLE"])
def test_service_calendar_blocker_precedes_new_population_planning(monkeypatch, state):
    from market_regime_alpha.interfaces import daily_service
    from tests.contracts.research_qualification.test_daily_prediction import plan
    frozen = plan()
    calls = []
    reads = SimpleNamespace(outcome_work_items=lambda **_: (), validate_configuration=lambda _: None,
        missing_elapsed_session_pairs=lambda _: pytest.fail("unverified calendar reached Prediction planning"))
    def refresh(*args, **kwargs):
        calls.append(kwargs)
        return {"state": "BLOCKED", "reason_code": "CALENDAR_CIVIL_DATE_UNOBSERVED", "coverage": {"state": state}}
    monkeypatch.setattr(daily_service, "refresh_calendar", refresh)
    result = daily_service.daily_tick(SimpleNamespace(daily_prediction_reads=reads), frozen, None,
        worker_id="test", maximum_steps=2, before_action=lambda: None)
    assert result["state"] == "CALENDAR_CONTINUITY_BLOCKED"
    assert result["calendar_continuity"]["coverage"]["state"] == state
    assert calls[0]["experimental_model_use_id"] == frozen.experimental_model_use_id
