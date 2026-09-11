"""Terminal continuation requires positive owner facts, never an error allowlist."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockProspectiveNormalizer
from market_regime_alpha.market.application.prospective_runtime import (
    ProspectiveArchiveRuntimeApplication, ProspectiveRuntimeIntegrityError,
    compile_prospective_runtime_plan,
)
from market_regime_alpha.market.domain import CaptureStatus, ProviderCapture, SourceAvailabilityStatus, TemporalEnvelope
from market_regime_alpha.market.ports import ArchiveTradingSession
from market_regime_alpha.market.ports.archive_operations import ArchiveTerminalNormalizerFailure
from market_regime_alpha.runtime.ports import ArtifactRecord, RunTrace, StepTrace
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import ContentHash, TradingSessionId
from tests.contracts.market.test_prospective_archive_planner import _manifest


def _case():
    manifest = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
    run = next(item for item in plan.capture_runs if item.schedule_slot == "OUTCOME_PRE_OPEN")
    item = run.slices[0]
    payload = {"error_code": "0", "error_message": "success",
               "fields": ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"],
               "query": json.loads(item.capture_request.resource), "rows": []}
    content = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    artifact = ArtifactRecord(uuid4(), sha256_bytes(content), len(content), "application/json",
                              "fixture", "AVAILABLE", None, None)
    started = run.window_start + timedelta(minutes=1)
    capture = ProviderCapture(
        uuid4(), item.capture_request.provider_product_id, item.capture_request.capture_key,
        ContentHash(canonical_json_sha256(item.capture_request)), CaptureStatus.CAPTURED,
        TemporalEnvelope(None, SourceAvailabilityStatus.UNKNOWN, None, started,
                         started + timedelta(seconds=1), started + timedelta(seconds=2), started + timedelta(seconds=2)),
        artifact.artifact_id, None, None, "UTF-8",
    )
    evidence = _bind(capture, artifact)
    step = run.steps[0]
    trace = RunTrace(run.run_id, plan.schedule.schedule_id, run.fire_key, "PROSPECTIVE", plan.code_sha,
        uuid4(), plan.config_sha256, "FAILED", 3, (StepTrace(uuid4(), step.step_key, step.step_kind,
            step.implementation, step.implementation_version, step.request_hash, step.input_evidence_hash,
            step.retry_policy.deadline, "FAILED", 1, None, ("FAILED_TERMINAL",), "NORMALIZER_OUTPUT_REJECTED"),))
    generation = manifest.start_request.prospective_generation
    day = datetime(2026, 9, 7, tzinfo=UTC)
    session = ArchiveTradingSession(TradingSessionId(generation.outcome_session_id), "XSHG", day.date(),
        day + timedelta(hours=1, minutes=30), day + timedelta(hours=3, minutes=30),
        day + timedelta(hours=5), day + timedelta(hours=7))
    return SimpleNamespace(plan=plan, run=run, evidence=evidence, content=content, trace=trace,
                           session=session, payload=payload, reads=[], registrations=[])


def _bind(capture, artifact):
    return ArchiveTerminalNormalizerFailure(capture, artifact,
        canonical_json_sha256({"capture": capture, "artifact_hash": artifact.content_sha256,
                               "artifact_size": artifact.size_bytes}),
        canonical_json_sha256({"capture_id": capture.capture_id,
                               "normalizer_contract": BaoStockProspectiveNormalizer.contract}))


def _application(case):
    def owner_read(**kwargs):
        case.reads.append(kwargs)
        return case.evidence

    return ProspectiveArchiveRuntimeApplication(
        runtime=SimpleNamespace(schedule_run=lambda *args: case.registrations.append(args),
                                inspect_run=lambda _: case.trace),
        artifacts=object(), archives=object(), operations=object(),
        database_clock=SimpleNamespace(now=lambda: case.run.window_end + timedelta(seconds=1)),
        due_query=lambda _: (), terminal_capture_reconciliation=SimpleNamespace(terminal_normalizer_failure=owner_read),
        manifest_reader=lambda *_: case.content,
        trading_sessions=SimpleNamespace(exact=lambda **_: case.session, sessions=lambda **_: (case.session,)),
    )


def _register(case):
    _application(case)._register_run(case.plan, case.run, config_artifact_id=case.trace.config_artifact_id, actor_id="fixture")


def test_verified_preopen_failure_repeats_readonly_and_preserves_terminal_trace():
    case = _case()
    before = case.trace
    _register(case)
    _register(case)
    assert case.trace == before
    assert case.trace.run_state == "FAILED"
    assert case.trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    assert len(case.registrations) == len(case.reads) == 2
    assert case.reads[0] == case.reads[1] == dict(run_id=case.run.run_id,
        step_id=case.trace.steps[0].step_id, market_archive_id=case.plan.market_archive_id,
        market_archive_slice_id=case.run.slices[0].plan.market_archive_slice_id, fence_token=1)


@pytest.mark.parametrize("change", ["unknown_effect", "prior_unknown", "active", "missing_owner", "capture_hash",
    "normalizer_hash", "capture_identity", "source_tamper", "nonempty", "provider_error", "query", "fields",
    "duplicate_keys", "mature", "wrong_session", "within_window"])
def test_only_exact_elapsed_known_empty_failure_can_continue(change):
    case = _case()
    if change == "unknown_effect":
        case.trace = replace(case.trace, steps=(replace(case.trace.steps[0], latest_attempt_error_code="EXTERNAL_EFFECT_UNKNOWN"),))
    elif change == "prior_unknown":
        case.trace = replace(case.trace, steps=(replace(case.trace.steps[0], attempt_states=("WAITING_UNKNOWN_EFFECT", "FAILED_TERMINAL")),))
    elif change == "active":
        case.trace = replace(case.trace, steps=(replace(case.trace.steps[0], state="RUNNING", attempt_states=("RUNNING",)),))
    elif change == "missing_owner":
        case.evidence = None
    elif change == "capture_hash":
        case.evidence = replace(case.evidence, capture_result_hash="0" * 64)
    elif change == "normalizer_hash":
        case.evidence = replace(case.evidence, normalization_request_hash="0" * 64)
    elif change == "capture_identity":
        case.evidence = _bind(replace(case.evidence.capture, capture_key="wrong-capture"), case.evidence.artifact)
    elif change == "source_tamper":
        case.content += b" "
    elif change in {"nonempty", "provider_error", "query", "fields", "duplicate_keys"}:
        if change == "nonempty":
            case.payload["rows"] = [["untrusted observation"]]
        elif change == "provider_error":
            case.payload["error_code"] = "1"
        elif change == "query":
            case.payload["query"]["code"] = "sh.600001"
        elif change == "fields":
            case.payload["fields"] = []
        case.content = json.dumps(case.payload).encode()
        if change == "duplicate_keys":
            case.content = case.content.replace(b'{"error_code":', b'{"rows": [["hidden"]], "error_code":', 1)
        artifact = replace(case.evidence.artifact, content_sha256=sha256_bytes(case.content), size_bytes=len(case.content))
        case.evidence = _bind(case.evidence.capture, artifact)
    elif change == "mature":
        case.session = replace(case.session, open_at=case.evidence.capture.temporal.capture_started_at - timedelta(minutes=5))
    elif change == "wrong_session":
        case.session = replace(case.session, session_id=TradingSessionId(uuid4()))
    application = _application(case)
    if change == "within_window":
        application._database_clock = SimpleNamespace(now=lambda: case.run.window_end)
    with pytest.raises((ProspectiveRuntimeIntegrityError, ValueError)):
        application._register_run(case.plan, case.run, config_artifact_id=case.trace.config_artifact_id, actor_id="fixture")
    assert case.trace.run_state == "FAILED"
    if change in {"unknown_effect", "prior_unknown", "active", "within_window"}:
        assert case.reads == []
