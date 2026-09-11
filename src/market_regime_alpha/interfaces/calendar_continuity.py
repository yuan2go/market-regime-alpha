"""A bounded calendar handoff inside the existing owned service Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import re
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.infrastructure.postgres.prospective_operation_session import daily_research_admission
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_calendar_normalizer import BaoStockCalendarNormalizer, CALENDAR_HORIZON_DAYS
from market_regime_alpha.market.ports import CaptureRequest, MarketProvider
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.domain import ExternalEffectClass, RetryPolicy, RunSpec, RuntimeMode, ScheduleSpec, StepDependency, StepSpec
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.runtime.ports import RunTrace
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_REFRESH_AGE = timedelta(days=7)
_LOW_HORIZON_DAYS = 30


@dataclass(frozen=True, slots=True)
class CalendarRefreshPlan:
    provider_product_id: UUID
    requested_at: datetime
    coverage_through: date
    code_sha: str

    def __post_init__(self) -> None:
        require_utc(self.requested_at, field="requested_at")
        if not re.fullmatch(r"[0-9a-f]{40}", self.code_sha) or not 1 <= (self.coverage_through - self.coverage_from).days + 1 <= CALENDAR_HORIZON_DAYS:
            raise ValueError("CALENDAR_FROZEN_PLAN_INVALID")

    @property
    def coverage_from(self) -> date:
        return self.requested_at.astimezone(_SHANGHAI).date()

    @property
    def identity(self) -> UUID:
        return uuid5(self.provider_product_id, "calendar:" + self.coverage_from.isoformat() + ":XSHG")

    @property
    def run_id(self) -> UUID:
        return uuid5(self.identity, "calendar-collection:1")

    @property
    def query(self) -> BaoStockArchiveQuery:
        return BaoStockArchiveQuery(BaoStockArchiveQueryKind.TRADE_DATES, self.coverage_from, self.coverage_through)

    @property
    def capture_key(self) -> str:
        return "calendar-continuity:" + self.coverage_from.isoformat() + ":XSHG"

    @property
    def content(self) -> bytes:
        return (json.dumps({"schema": "calendar-continuity-v1", "provider_product_id": str(self.provider_product_id),
            "requested_at": self.requested_at.isoformat(), "coverage_through": self.coverage_through.isoformat(),
            "code_sha": self.code_sha, "query": json.loads(self.query.resource)}, sort_keys=True, separators=(",", ":")) + "\n").encode()

    @property
    def content_sha256(self) -> str:
        return sha256(self.content).hexdigest()

    @classmethod
    def decode(cls, content: bytes) -> CalendarRefreshPlan:
        value = json.loads(content)
        if set(value) != {"schema", "provider_product_id", "requested_at", "coverage_through", "code_sha", "query"} or value["schema"] != "calendar-continuity-v1":
            raise ArtifactIntegrityError("CALENDAR_FROZEN_PLAN_SHAPE_DIFFERS")
        plan = cls(UUID(value["provider_product_id"]), datetime.fromisoformat(value["requested_at"]), date.fromisoformat(value["coverage_through"]), value["code_sha"])
        if plan.content != content:
            raise ArtifactIntegrityError("CALENDAR_FROZEN_PLAN_BYTES_DIFFER")
        return plan


def calendar_steps(plan: CalendarRefreshPlan) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    steps = tuple(StepSpec(key, kind, "market.daily_research.calendar." + key, "1", ordinal, True,
        canonical_json_sha256({"calendar_sha256": plan.content_sha256, "step": key}), None,
        RetryPolicy(1 if kind == "CAPTURE" else 3, (), frozenset()),
        ExternalEffectClass.CONTENT_PUT if kind == "CAPTURE" else ExternalEffectClass.NONE,
    ) for ordinal, (key, kind) in enumerate((("capture-calendar", "CAPTURE"), ("normalize-calendar", "NORMALIZE_PIT")), 1))
    return steps, (StepDependency(steps[0].step_key, steps[1].step_key),)


def _verify_run(trace: RunTrace, plan: CalendarRefreshPlan) -> None:
    steps, _ = calendar_steps(plan)
    if (trace.run_id != plan.run_id or trace.schedule_id != uuid5(plan.provider_product_id, "daily-calendar-collection")
            or trace.fire_key != f"daily-calendar:{plan.identity}:round:1" or trace.runtime_mode != "SHADOW"
            or trace.code_sha != plan.code_sha or str(trace.config_hash) != plan.content_sha256 or len(trace.steps) != 2
            or any((actual.step_key, actual.step_kind, actual.implementation, actual.implementation_version, actual.request_hash)
                != (expected.step_key, expected.step_kind, expected.implementation, expected.implementation_version, expected.request_hash)
                for actual, expected in zip(trace.steps, steps))):
        raise ArtifactIntegrityError("CALENDAR_FROZEN_RUNTIME_DIFFERS")


def refresh_calendar(app: TargetApplication, *, provider_product_id: UUID, code_sha: str, provider: MarketProvider,
    worker_id: str, before_action: Callable[[], None], observed_at: datetime | None = None, expires_at: datetime | None = None,
    experimental_model_use_id: UUID | None = None,
) -> dict[str, Any]:
    """At most one new actual observation per DB civil date; no unknown-effect retry."""
    before_action()
    now = app.daily_prediction_reads.now()
    if experimental_model_use_id is not None:
        current_expiry = app.daily_prediction_reads.experimental_model_use_record(experimental_model_use_id)["expires_at"]
        if expires_at is not None and expires_at != current_expiry:
            raise ArtifactIntegrityError("CALENDAR_MODEL_USE_EXPIRY_DIFFERS")
        expires_at = current_expiry
    if observed_at is not None and (require_utc(observed_at, field="observed_at") > now or observed_at.astimezone(_SHANGHAI).date() != now.astimezone(_SHANGHAI).date()):
        raise RuntimeStateConflictError("CALENDAR_OBSERVATION_CLOCK_DIFFERS")
    unresolved = app.calendar_continuity_reads.unresolved_work(provider_product_id)
    if unresolved:
        return {"state": "BLOCKED", "reason_code": "CALENDAR_ATTEMPT_REQUIRES_RECONCILIATION", "unresolved_work": unresolved}
    coverage = app.calendar_continuity_reads.calendar_coverage(provider_product_id, now)
    today = now.astimezone(_SHANGHAI).date()
    horizon = today + timedelta(days=CALENDAR_HORIZON_DAYS - 1)
    if expires_at is not None:
        require_utc(expires_at, field="expires_at")
        if now >= expires_at:
            return {"state": "NOT_DUE", "reason_code": "CURRENT_MODEL_USE_EXPIRED", "coverage": coverage}
        horizon = min(horizon, expires_at.astimezone(_SHANGHAI).date())
    minimum_horizon = min(horizon, today + timedelta(days=_LOW_HORIZON_DAYS - 1))
    if (coverage["state"] == "VERIFIED" and coverage["coverage_from"] <= today
            and coverage["coverage_through"] >= minimum_horizon and now - coverage["known_at"] < _REFRESH_AGE):
        return {"state": "NOT_DUE", "reason_code": "VERIFIED_CALENDAR_FRESH", "coverage": coverage}
    plan = CalendarRefreshPlan(provider_product_id, now, horizon, code_sha)
    frozen = app.daily_prediction_reads.run_plan_content(plan.run_id)
    if frozen is not None:
        existing_plan = CalendarRefreshPlan.decode(frozen)
        if existing_plan.identity != plan.identity or existing_plan.provider_product_id != provider_product_id:
            raise ArtifactIntegrityError("CALENDAR_REFRESH_IDENTITY_DIFFERS")
        plan = existing_plan
    try:
        trace = app.runtime.inspect_run(plan.run_id)
    except RuntimeNotFoundError:
        trace = None
    if trace is not None:
        _verify_run(trace, plan)
        if trace.run_state in {"FAILED", "WAITING", "SUCCEEDED"}:
            reason = "CALENDAR_RUN_" + trace.run_state
            if trace.run_state == "SUCCEEDED" and coverage["state"] != "VERIFIED":
                reason = coverage.get("reason_code", "CALENDAR_COVERAGE_UNAVAILABLE")
            return {"state": "OBSERVATION_RECORDED" if trace.run_state == "SUCCEEDED" else "BLOCKED", "reason_code": reason, "run_id": plan.run_id, "coverage": coverage}
    if plan.code_sha != code_sha:
        raise ArtifactIntegrityError("CALENDAR_PENDING_IMPLEMENTATION_CHANGED")
    with daily_research_admission(prediction_id=plan.identity, code_sha=plan.code_sha, config_sha256=plan.content_sha256, collection_phase="calendar"):
        trace = _collect_calendar(app, plan, provider, worker_id, before_action)
    coverage = app.calendar_continuity_reads.calendar_coverage(provider_product_id, app.daily_prediction_reads.now())
    reason = "CALENDAR_RUN_" + trace.run_state
    if trace.run_state == "SUCCEEDED" and coverage["state"] != "VERIFIED":
        reason = coverage.get("reason_code", "CALENDAR_COVERAGE_UNAVAILABLE")
    return {"state": "REFRESHED" if trace.run_state == "SUCCEEDED" and coverage["state"] == "VERIFIED" else "BLOCKED",
        "reason_code": reason, "run_id": plan.run_id, "coverage": coverage}


def _collect_calendar(app: TargetApplication, plan: CalendarRefreshPlan, provider: MarketProvider, worker_id: str, before_action: Callable[[], None]) -> RunTrace:
    def context(key: str) -> CommandContext:
        return CommandContext("calendar:" + str(plan.run_id) + ":" + key, ActorType.WORKER, worker_id, "CALENDAR_CONTINUITY")
    before_action()
    artifact = app.artifacts.publish(plan.content, media_type="application/json", context=context("plan"))
    schedule_id = uuid5(plan.provider_product_id, "daily-calendar-collection")
    app.runtime.create_schedule(ScheduleSpec(schedule_id, "daily-calendar-collection-" + plan.provider_product_id.hex, 1, RuntimeMode.SHADOW, None,
        "Asia/Shanghai", canonical_json_sha256(("CAPTURE", "NORMALIZE_PIT")), True),
        CommandContext("calendar-schedule:" + str(schedule_id), ActorType.WORKER, "calendar-continuity", "CALENDAR_CONTINUITY"))
    steps, dependencies = calendar_steps(plan)
    app.runtime.schedule_run(RunSpec(plan.run_id, schedule_id, f"daily-calendar:{plan.identity}:round:1", RuntimeMode.SHADOW,
        plan.requested_at, plan.requested_at, plan.code_sha, artifact.artifact_id, artifact.content_sha256), steps, dependencies, context("run"))
    trace = app.runtime.inspect_run(plan.run_id)
    _verify_run(trace, plan)
    if trace.run_state == "QUEUED":
        app.runtime.start_run(plan.run_id, context("start"))
    for _ in range(2):
        before_action()
        trace = app.runtime.inspect_run(plan.run_id)
        if trace.run_state != "RUNNING":
            break
        step = next((item for item in trace.steps if item.state == "READY"), None)
        if step is None:
            break
        if step.step_kind == "CAPTURE" and app.daily_prediction_reads.now().astimezone(_SHANGHAI).date() != plan.coverage_from:
            raise RuntimeStateConflictError("CALENDAR_CAPTURE_CIVIL_DATE_CHANGED")
        claim = app.runtime.claim_next(run_id=plan.run_id, step_id=step.step_id, worker_id=worker_id,
            lease_duration=timedelta(minutes=2), context=context("claim:" + step.step_key + ":" + str(step.current_fence + 1)))
        if claim is None:
            break
        app.runtime.start_attempt(claim, context("start:" + str(claim.attempt_id)))
        before_action()
        if step.step_kind == "CAPTURE":
            if claim.attempt_no != 1 or app.daily_prediction_reads.now().astimezone(_SHANGHAI).date() != plan.coverage_from:
                raise RuntimeStateConflictError("CALENDAR_PROVIDER_EFFECT_REQUIRES_RECONCILIATION")
            app.market.capture(CaptureRequest(plan.provider_product_id, plan.capture_key, plan.query.resource, ContentHash(canonical_json_sha256({"headers": {}}))),
                provider, context(step.step_key), runtime_claim=claim)
        else:
            capture_id = app.daily_prediction_reads.capture_by_key(plan.provider_product_id, plan.capture_key)
            app.market.normalize(capture_id, BaoStockCalendarNormalizer(plan.query), context(step.step_key), runtime_claim=claim)
    return app.runtime.inspect_run(plan.run_id)
