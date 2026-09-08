"""Bounded Market capture/normalization steps inside the existing Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from market_regime_alpha.infrastructure.providers.baostock_archive import (
    BaoStockArchiveQuery,
    BaoStockArchiveQueryKind,
    BaoStockSession,
    BaoStockArchiveProvider,
    BaoStockSdk,
)
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer
from market_regime_alpha.interfaces.daily_research import encode_daily_plan, decode_daily_plan
from market_regime_alpha.market.ports import CaptureRequest, MarketProvider, ProviderResponse
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.domain import (
    RuntimeMode,
    RunSpec,
    ScheduleSpec,
    StepSpec,
    StepDependency,
    RetryPolicy,
    ExternalEffectClass,
)
from market_regime_alpha.runtime.errors import RuntimeStateConflictError, RuntimeNotFoundError
from market_regime_alpha.runtime.ports import AttemptClaim, RunTrace, StepTrace
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication


@dataclass(frozen=True, slots=True)
class DailyCollectionPlan:
    prediction: DailyPredictionPlan
    phase: str
    round: int
    requested_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.requested_at, field="requested_at")
        if self.phase not in {"input", "outcome", "population"} or isinstance(self.round, bool) or not 1 <= self.round <= 16:
            raise ValueError("daily collection requires an explicit bounded phase/round")
        if self.phase == "population" and (self.prediction.classification_scheme, self.prediction.classification_code) != ("INDEX_MEMBERSHIP", "CSI300"):
            raise ValueError("DAILY_MEMBERSHIP_PRODUCT_SCOPE_UNSUPPORTED")

    @property
    def run_id(self) -> UUID:
        return uuid5(self.prediction.prediction_id, self.phase + "-collection:" + str(self.round))

    @property
    def schedule_code(self) -> str:
        return "daily-" + self.phase + "-collection-" + self.prediction.experimental_model_use_id.hex

    @property
    def content(self) -> bytes:
        return (
            json.dumps(
                {
                    "schema": "daily-market-collection-v1",
                    "prediction": json.loads(encode_daily_plan(self.prediction)),
                    "phase": self.phase,
                    "round": self.round,
                    "requested_at": self.requested_at.isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

    @property
    def content_sha256(self) -> str:
        return sha256(self.content).hexdigest()

    @classmethod
    def decode(cls, content: bytes) -> DailyCollectionPlan:
        value = json.loads(content)
        if set(value) != {"schema", "prediction", "phase", "round", "requested_at"} or value["schema"] != "daily-market-collection-v1":
            raise ValueError("daily collection schema differs")
        return cls(
            decode_daily_plan(json.dumps(value["prediction"]).encode()),
            value["phase"],
            value["round"],
            datetime.fromisoformat(value["requested_at"]),
        )


def collection_steps(plan: DailyCollectionPlan) -> tuple[tuple[StepSpec, ...], tuple[StepDependency, ...]]:
    roster = tuple(
        (prefix + "-" + instrument.hex, kind)
        for instrument in plan.prediction.instrument_ids
        for prefix, kind in (("capture", "CAPTURE"), ("normalize", "NORMALIZE_PIT"))
    )
    if plan.phase == "population":
        roster = (("capture-membership", "CAPTURE"), ("normalize-membership", "NORMALIZE_PIT"))
    # Match canonical Market Capture semantics: content-addressed external bytes.
    # A single capture attempt stops unknown effects; only committed receipts replay.
    steps = tuple(
        StepSpec(
            key,
            kind,
            "market.daily_research." + plan.phase + "." + key,
            "1",
            ordinal,
            True,
            canonical_json_sha256({"collection_sha256": plan.content_sha256, "step": key}),
            None,
            RetryPolicy(1 if kind == "CAPTURE" else 3, (), frozenset()),
            ExternalEffectClass.CONTENT_PUT if kind == "CAPTURE" else ExternalEffectClass.NONE,
        )
        for ordinal, (key, kind) in enumerate(roster, 1)
    )
    return steps, tuple(StepDependency(first.step_key, second.step_key) for first, second in zip(steps, steps[1:]))


def collect_daily(
    app: TargetApplication,
    plan: DailyCollectionPlan,
    provider: MarketProvider,
    *,
    worker_id: str,
    maximum_steps: int,
    before_action: Callable[[], None],
) -> RunTrace:
    if not worker_id or not 1 <= maximum_steps <= 128:
        raise ValueError("daily collection requires a bounded worker budget")
    before_action()
    frozen = plan.prediction
    try:
        existing = app.runtime.inspect_run(plan.run_id)
    except RuntimeNotFoundError:
        existing = None
    if existing is not None:
        if str(existing.config_hash) != plan.content_sha256 or existing.code_sha != frozen.code_sha:
            raise RuntimeStateConflictError("daily collection frozen Runtime identity differs")
        if existing.run_state == "SUCCEEDED":
            return existing
    ready = app.daily_prediction_reads.observe(frozen)
    now = app.daily_prediction_reads.now()
    if (
        plan.phase in {"input", "population"}
        and (now < ready.input_event_end or (now >= ready.target_window_start and existing is None))
        or plan.phase == "outcome"
        and now < ready.target_window_end
    ):
        raise RuntimeStateConflictError("DAILY_CAPTURE_OUTSIDE_LEGAL_WINDOW")
    roster = app.daily_prediction_reads.capture_roster(frozen, outcome=plan.phase == "outcome")

    def context(key: str) -> CommandContext:
        return CommandContext("daily-collection:" + str(plan.run_id) + ":" + key, ActorType.WORKER, worker_id, "DAILY_MARKET_OBSERVATION")

    artifact = app.artifacts.publish(plan.content, media_type="application/json", context=context("plan"))
    steps, dependencies = collection_steps(plan)
    schedule_id = uuid5(frozen.experimental_model_use_id, "daily-" + plan.phase + "-collection")
    app.runtime.create_schedule(
        ScheduleSpec(
            schedule_id,
            plan.schedule_code,
            1,
            RuntimeMode.SHADOW,
            None,
            "Asia/Shanghai",
            canonical_json_sha256(("CAPTURE", "NORMALIZE_PIT")),
            True,
        ),
        CommandContext(
            "daily-collection-schedule:" + str(schedule_id), ActorType.WORKER, "daily-model-research", "DAILY_MARKET_OBSERVATION"
        ),
    )
    app.runtime.schedule_run(
        RunSpec(
            plan.run_id,
            schedule_id,
            "daily-" + plan.phase + ":" + str(frozen.prediction_id) + ":round:" + str(plan.round),
            RuntimeMode.SHADOW,
            plan.requested_at,
            frozen.decision_time,
            frozen.code_sha,
            artifact.artifact_id,
            artifact.content_sha256,
            parent_run_id=frozen.runtime_run_id if plan.phase == "outcome" else None,
        ),
        steps,
        dependencies,
        context("run"),
    )
    trace = app.runtime.inspect_run(plan.run_id)
    if trace.run_state == "QUEUED":
        app.runtime.start_run(plan.run_id, context("start"))
    app.runtime.recover_expired(actor_id=worker_id, reason_code="DAILY_RESTART", run_id=plan.run_id)
    for _ in range(maximum_steps):
        before_action()
        trace = app.runtime.inspect_run(plan.run_id)
        if trace.run_state != "RUNNING":
            break
        step = next((s for s in trace.steps if s.state == "READY"), None)
        if step is None:
            break
        claim = app.runtime.claim_next(
            run_id=plan.run_id,
            step_id=step.step_id,
            worker_id=worker_id,
            lease_duration=timedelta(minutes=2),
            context=context("claim:" + step.step_key + ":" + str(step.current_fence + 1)),
        )
        if claim is None:
            break
        app.runtime.start_attempt(claim, context("start:" + str(claim.attempt_id)))
        if step.step_kind == "CAPTURE" and plan.phase in {"input", "population"} and app.daily_prediction_reads.now() >= ready.target_window_start:
            app.runtime.fail_attempt(claim, error_class="RESEARCH", error_code="MISSED_DATA_WINDOW", context=context("missed-window"))
            break
        try:
            _execute_collection_step(
                app=app,
                plan=plan,
                frozen=frozen,
                roster=roster,
                step=step,
                claim=claim,
                provider=provider,
                context=context,
                before_action=before_action,
            )
        except Exception:
            _fail_live_collection_claim(
                app, plan, claim, context, before_action
            )
            raise
    return app.runtime.inspect_run(plan.run_id)


def _execute_collection_step(
    *,
    app: TargetApplication,
    plan: DailyCollectionPlan,
    frozen: DailyPredictionPlan,
    roster: tuple[tuple[UUID, str, Any], ...],
    step: StepTrace,
    claim: AttemptClaim,
    provider: MarketProvider,
    context: Callable[[str], CommandContext],
    before_action: Callable[[], None],
) -> None:
    if plan.phase == "population":
        # This is the database-observed request date, never a guessed session.
        observation_date = plan.requested_at.astimezone(
            ZoneInfo("Asia/Shanghai")
        ).date()
        query = BaoStockArchiveQuery(
            BaoStockArchiveQueryKind.CSI300_MEMBERS,
            observation_date,
            observation_date,
        )
        capture_key = (
            "daily-population:"
            + str(frozen.prediction_id)
            + ":round:"
            + str(plan.round)
        )
    else:
        instrument, code, session_date = next(
            row for row in roster if step.step_key.endswith(row[0].hex)
        )
        query = BaoStockArchiveQuery(
            BaoStockArchiveQueryKind.HISTORY_DAILY_RAW,
            session_date,
            session_date,
            code,
        )
        capture_key = (
            "daily-"
            + plan.phase
            + ":"
            + str(frozen.prediction_id)
            + ":"
            + str(instrument)
            + ":round:"
            + str(plan.round)
        )
    before_action()
    if step.step_kind == "CAPTURE":
        if claim.attempt_no != 1:
            raise RuntimeStateConflictError(
                "DAILY_PROVIDER_EFFECT_REQUIRES_RECONCILIATION"
            )
        app.market.capture(
            CaptureRequest(
                frozen.provider_product_id,
                capture_key,
                query.resource,
                ContentHash(canonical_json_sha256({"headers": {}})),
            ),
            provider,
            context(step.step_key),
            runtime_claim=claim,
        )
    else:
        capture_id = app.daily_prediction_reads.capture_by_key(
            frozen.provider_product_id, capture_key
        )
        app.market.normalize(
            capture_id,
            BaoStockArchiveNormalizer(
                query, app.market_revision_lineage, app.archive_trading_sessions
            ),
            context(step.step_key),
            runtime_claim=claim,
        )


def _fail_live_collection_claim(
    app: TargetApplication,
    plan: DailyCollectionPlan,
    claim: AttemptClaim,
    context: Callable[[str], CommandContext],
    before_action: Callable[[], None],
) -> None:
    try:
        before_action()
        trace = app.runtime.inspect_run(plan.run_id)
        step = next(item for item in trace.steps if item.step_id == claim.step_id)
        if (
            step.current_attempt_id == claim.attempt_id
            and step.state in {"CLAIMED", "RUNNING"}
        ):
            app.runtime.fail_attempt(
                claim,
                error_class="RESEARCH",
                error_code="DAILY_COLLECTION_STEP_FAILED",
                context=context("fail:" + str(claim.attempt_id)),
            )
    except (RuntimeError, ValueError, StopIteration):
        return


class PerCaptureBaoStockProvider:
    """Open a bounded SDK session only when Market actually asks for an effect."""

    def __init__(self, sdk: BaoStockSdk, *, timeout_seconds: float, maximum_rows: int, maximum_response_bytes: int) -> None:
        self.sdk = sdk
        self.timeout_seconds = timeout_seconds
        self.maximum_rows = maximum_rows
        self.maximum_response_bytes = maximum_response_bytes

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        from market_regime_alpha.interfaces.prospective_operation_guard import quiet_provider_output

        with (
            quiet_provider_output(),
            BaoStockSession(
                self.sdk,
                timeout_seconds=self.timeout_seconds,
                maximum_attempts=1,
                maximum_rows=self.maximum_rows,
                maximum_response_bytes=self.maximum_response_bytes,
            ) as session,
        ):
            return BaoStockArchiveProvider(session).capture(request)
