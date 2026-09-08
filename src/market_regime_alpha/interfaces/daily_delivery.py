"""Durable report delivery on the existing Runtime; never prediction Authority."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid5

from market_regime_alpha.interfaces.daily_research import render_daily_report
from market_regime_alpha.notifications import Notifier
from market_regime_alpha.research_qualification.domain.daily_prediction import (
    DailyPredictionPlan,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.ports.daily_prediction import (
    DailyPredictionReads,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import RunTrace
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc

if TYPE_CHECKING:
    from market_regime_alpha.bootstrap import TargetApplication


_CHANNEL = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_ATTEMPT_STATES = frozenset({"DELIVERED", "PROVEN_NOT_SENT", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class DailyDeliveryAttempt:
    state: str
    reason_code: str
    remote_receipt_id: str | None = None

    def __post_init__(self) -> None:
        if self.state not in _ATTEMPT_STATES:
            raise ValueError("daily delivery attempt state is unsupported")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", self.reason_code):
            raise ValueError("daily delivery reason code is invalid")
        if self.state == "DELIVERED" and not self.remote_receipt_id:
            raise ValueError("delivered result requires a remote receipt identity")
        if self.state != "DELIVERED" and self.remote_receipt_id is not None:
            raise ValueError(
                "non-delivered result cannot claim a remote delivery receipt"
            )


class DailyDeliveryAdapter(Protocol):
    channel: str

    def deliver(
        self, content: str, *, idempotency_key: str
    ) -> DailyDeliveryAttempt: ...


class LegacyNotifierDeliveryAdapter:
    """Conservative adapter: a legacy failure cannot prove remote non-delivery."""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier
        self.channel = notifier.channel

    def deliver(
        self, content: str, *, idempotency_key: str
    ) -> DailyDeliveryAttempt:
        del idempotency_key
        result = self._notifier.send_text(content)
        if result.success:
            return DailyDeliveryAttempt(
                "DELIVERED",
                "LEGACY_NOTIFIER_ACKNOWLEDGED",
                canonical_json_sha256(
                    {"channel": result.channel, "message": result.message}
                ),
            )
        return DailyDeliveryAttempt("UNKNOWN", "LEGACY_NOTIFIER_RESULT_UNKNOWN")


@dataclass(frozen=True, slots=True)
class DailyDeliveryPlan:
    prediction_id: UUID
    experimental_model_use_id: UUID
    model_version_id: UUID
    channel: str
    report: ArtifactBinding
    requested_at: datetime
    expires_at: datetime
    code_sha: str

    def __post_init__(self) -> None:
        require_utc(self.requested_at, field="delivery requested_at")
        require_utc(self.expires_at, field="delivery expires_at")
        if not _CHANNEL.fullmatch(self.channel):
            raise ValueError("daily delivery channel is invalid")
        if self.expires_at <= self.requested_at:
            raise ValueError("daily delivery expiry must follow its request")

    @property
    def run_id(self) -> UUID:
        return uuid5(self.prediction_id, "report-delivery:" + self.channel)

    @property
    def schedule_id(self) -> UUID:
        return uuid5(
            self.experimental_model_use_id,
            "daily-delivery-schedule:" + self.channel,
        )

    @property
    def content(self) -> bytes:
        payload = asdict(self)
        payload["report"] = {
            "artifact_id": str(self.report.artifact_id),
            "content_sha256": str(self.report.content_sha256),
            "size_bytes": self.report.size_bytes,
        }
        for key in ("prediction_id", "experimental_model_use_id", "model_version_id"):
            payload[key] = str(payload[key])
        for key in ("requested_at", "expires_at"):
            payload[key] = getattr(self, key).isoformat()
        return (
            json.dumps(
                {"schema": "daily-report-delivery-plan-v1", "plan": payload},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

    @property
    def content_sha256(self) -> str:
        return sha256(self.content).hexdigest()

    @classmethod
    def decode(cls, content: bytes) -> DailyDeliveryPlan:
        root = json.loads(content)
        if (
            not isinstance(root, dict)
            or set(root) != {"schema", "plan"}
            or root["schema"] != "daily-report-delivery-plan-v1"
        ):
            raise ValueError("daily delivery plan schema differs")
        value = root["plan"]
        if not isinstance(value, dict) or set(value) != {
            "prediction_id",
            "experimental_model_use_id",
            "model_version_id",
            "channel",
            "report",
            "requested_at",
            "expires_at",
            "code_sha",
        }:
            raise ValueError("daily delivery plan fields differ")
        report = value["report"]
        if not isinstance(report, dict) or set(report) != {
            "artifact_id",
            "content_sha256",
            "size_bytes",
        }:
            raise ValueError("daily delivery report binding differs")
        return cls(
            prediction_id=UUID(value["prediction_id"]),
            experimental_model_use_id=UUID(value["experimental_model_use_id"]),
            model_version_id=UUID(value["model_version_id"]),
            channel=value["channel"],
            report=ArtifactBinding(
                UUID(report["artifact_id"]),
                report["content_sha256"],
                report["size_bytes"],
            ),
            requested_at=datetime.fromisoformat(value["requested_at"]),
            expires_at=datetime.fromisoformat(value["expires_at"]),
            code_sha=value["code_sha"],
        )


class DailyReportDelivery:
    def __init__(
        self,
        app: TargetApplication,
        reads: DailyPredictionReads,
        *,
        admission_scope: Callable[
            [DailyDeliveryPlan], AbstractContextManager[None]
        ],
        before_action: Callable[[], None] = lambda: None,
        lease_duration: timedelta = timedelta(minutes=2),
    ) -> None:
        if lease_duration <= timedelta(0) or lease_duration > timedelta(minutes=5):
            raise ValueError("daily delivery lease duration is invalid")
        self._app = app
        self._reads = reads
        self._admission_scope = admission_scope
        self._before_action = before_action
        self._lease_duration = lease_duration

    def deliver(
        self,
        plan: DailyPredictionPlan,
        adapter: DailyDeliveryAdapter | None,
        *,
        worker_id: str,
        expires_at: datetime | None = None,
        maximum_attempts: int = 1,
    ) -> dict[str, object]:
        if adapter is None:
            return {
                "state": "NOT_CONFIGURED",
                "prediction_id": plan.prediction_id,
                "delivery_attempted": False,
                "prediction_and_settlement_blocked": False,
            }
        if not worker_id or not 1 <= maximum_attempts <= 3:
            raise ValueError("daily delivery requires a bounded worker budget")
        if not _CHANNEL.fullmatch(adapter.channel):
            raise ValueError("daily delivery channel is invalid")
        projection = self._reads.forecast_projection(plan)
        _json_report, markdown = render_daily_report(plan, projection)
        report = self._reads.published_report(
            plan, "report-markdown", markdown
        )
        now = self._reads.now()
        desired = DailyDeliveryPlan(
            prediction_id=plan.prediction_id,
            experimental_model_use_id=plan.experimental_model_use_id,
            model_version_id=plan.model_version_id,
            channel=adapter.channel,
            report=report,
            requested_at=now,
            expires_at=expires_at or now + timedelta(hours=24),
            code_sha=plan.code_sha,
        )
        existing = self._reads.run_plan_content(desired.run_id)
        frozen = desired if existing is None else DailyDeliveryPlan.decode(existing)
        if (
            frozen.prediction_id != desired.prediction_id
            or frozen.experimental_model_use_id
            != desired.experimental_model_use_id
            or frozen.model_version_id != desired.model_version_id
            or frozen.channel != desired.channel
            or frozen.report != desired.report
            or frozen.code_sha != desired.code_sha
        ):
            raise ArtifactIntegrityError("daily delivery frozen identity changed")
        with self._admission_scope(frozen):
            return self._deliver_frozen(
                frozen,
                markdown,
                adapter,
                worker_id=worker_id,
                maximum_attempts=maximum_attempts,
            )

    def _deliver_frozen(
        self,
        frozen: DailyDeliveryPlan,
        markdown: bytes,
        adapter: DailyDeliveryAdapter,
        *,
        worker_id: str,
        maximum_attempts: int,
    ) -> dict[str, object]:
        self._register(frozen)
        self._app.runtime.recover_expired(
            actor_id=worker_id,
            reason_code="DAILY_DELIVERY_RESTART",
            run_id=frozen.run_id,
        )
        attempts_started = 0
        while attempts_started < maximum_attempts:
            trace = self._app.runtime.inspect_run(frozen.run_id)
            if trace.run_state == "SUCCEEDED":
                return self._status(frozen, "DELIVERED")
            if trace.run_state == "WAITING":
                response = self._attempt_response(frozen, trace)
                if (
                    response is not None
                    and response["state"] == "PROVEN_NOT_SENT"
                ):
                    if self._reads.now() >= frozen.expires_at:
                        self._app.runtime.resume_waiting_step(
                            run_id=frozen.run_id,
                            step_id=trace.steps[0].step_id,
                            resolution_code="EXTERNAL_EFFECT_PROVEN_ABSENT",
                            context=self._context(frozen, "expire-proven-absent"),
                        )
                        self._app.runtime.recover_expired(
                            actor_id=worker_id,
                            reason_code="DAILY_DELIVERY_EXPIRED",
                            run_id=frozen.run_id,
                        )
                        return self._status(
                            frozen, "EXPIRED", response=response
                        )
                    if len(trace.steps[0].attempt_states) >= 3:
                        return self._status(
                            frozen, "RETRY_EXHAUSTED", response=response
                        )
                    self._app.runtime.resume_waiting_step(
                        run_id=frozen.run_id,
                        step_id=trace.steps[0].step_id,
                        resolution_code="EXTERNAL_EFFECT_PROVEN_ABSENT",
                        context=self._context(
                            frozen,
                            "resume:" + str(len(trace.steps[0].attempt_states)),
                        ),
                    )
                    continue
                state = (
                    "DELIVERY_RECEIPT_RECONCILIATION_REQUIRED"
                    if response is not None and response["state"] == "DELIVERED"
                    else "DELIVERY_UNKNOWN_EXPIRED"
                    if self._reads.now() >= frozen.expires_at
                    else "DELIVERY_UNKNOWN"
                )
                return self._status(frozen, state, response=response)
            if trace.run_state in {"FAILED", "CANCELLED"}:
                return self._status(
                    frozen,
                    "EXPIRED" if self._reads.now() >= frozen.expires_at else "FAILED",
                )
            self._before_action()
            claim = self._app.runtime.claim_next(
                run_id=frozen.run_id,
                step_id=trace.steps[0].step_id,
                worker_id=worker_id,
                lease_duration=self._lease_duration,
                context=self._context(
                    frozen,
                    "claim:" + str(trace.steps[0].current_fence + 1),
                ),
            )
            if claim is None:
                return self._status(frozen, "NO_CLAIM")
            attempts_started += 1
            self._app.runtime.start_attempt(
                claim, self._context(frozen, "start:" + str(claim.attempt_id))
            )
            self._before_action()
            try:
                result = adapter.deliver(
                    markdown.decode("utf-8"),
                    idempotency_key="daily-delivery:" + str(frozen.run_id),
                )
            except Exception:
                result = DailyDeliveryAttempt(
                    "UNKNOWN", "DELIVERY_ADAPTER_EXCEPTION"
                )
            # The remote effect is outside all database transactions. Recheck
            # supervisor authority before recording its local result.
            self._before_action()
            response_artifact, response_value = self._publish_response(
                frozen, claim.attempt_no, result
            )
            if result.state == "DELIVERED":
                self._app.runtime.succeed_attempt(
                    claim,
                    result_hash=str(response_artifact.content_sha256),
                    context=self._context(frozen, "delivered:" + str(claim.attempt_no)),
                )
                return self._status(
                    frozen,
                    "DELIVERED",
                    response=response_value,
                )
            self._app.runtime.fail_attempt(
                claim,
                error_class="DELIVERY",
                error_code=result.reason_code,
                context=self._context(frozen, "failed:" + str(claim.attempt_no)),
            )
            if result.state != "PROVEN_NOT_SENT":
                return self._status(frozen, "DELIVERY_UNKNOWN")
        trace = self._app.runtime.inspect_run(frozen.run_id)
        response = self._attempt_response(frozen, trace)
        state = (
            "RETRY_PENDING"
            if response is not None and response["state"] == "PROVEN_NOT_SENT"
            else "DELIVERY_UNKNOWN"
        )
        return self._status(frozen, state, response=response)

    def _register(self, plan: DailyDeliveryPlan) -> None:
        config = self._app.artifacts.publish(
            plan.content,
            media_type="application/json",
            context=self._context(plan, "plan"),
        )
        step = StepSpec(
            "deliver-report",
            "RECORD_EVIDENCE",
            "research.daily_delivery.deliver-report",
            "1",
            1,
            True,
            canonical_json_sha256(
                {
                    "plan_sha256": plan.content_sha256,
                    "report_sha256": str(plan.report.content_sha256),
                    "channel": plan.channel,
                }
            ),
            str(plan.report.content_sha256),
            RetryPolicy(
                3,
                (timedelta(seconds=30), timedelta(minutes=5)),
                frozenset({"DELIVERY_PROVEN_NOT_SENT"}),
                plan.expires_at,
            ),
            ExternalEffectClass.IDEMPOTENT_REMOTE_COMMAND,
        )
        schedule = ScheduleSpec(
            plan.schedule_id,
            "daily-delivery-"
            + plan.experimental_model_use_id.hex
            + "-"
            + plan.channel,
            1,
            RuntimeMode.SHADOW,
            None,
            "Asia/Shanghai",
            canonical_json_sha256(
                ("RECORD_EVIDENCE", "research.daily_delivery.deliver-report")
            ),
            True,
        )
        self._app.runtime.create_schedule(
            schedule, self._context(plan, "schedule")
        )
        self._app.runtime.schedule_run(
            RunSpec(
                plan.run_id,
                plan.schedule_id,
                "daily-delivery:"
                + str(plan.prediction_id)
                + ":"
                + plan.channel,
                RuntimeMode.SHADOW,
                plan.requested_at,
                plan.requested_at,
                plan.code_sha,
                config.artifact_id,
                config.content_sha256,
                parent_run_id=uuid5(plan.prediction_id, "prediction-runtime"),
            ),
            (step,),
            (),
            self._context(plan, "run"),
        )
        trace = self._app.runtime.inspect_run(plan.run_id)
        if trace.run_state == "QUEUED":
            self._app.runtime.start_run(plan.run_id, self._context(plan, "start-run"))

    def _publish_response(
        self,
        plan: DailyDeliveryPlan,
        attempt_no: int,
        result: DailyDeliveryAttempt,
    ) -> tuple[ArtifactBinding, dict[str, object]]:
        value: dict[str, object] = {
            "schema": "daily-report-delivery-attempt-v1",
            "prediction_id": str(plan.prediction_id),
            "delivery_run_id": str(plan.run_id),
            "channel": plan.channel,
            "attempt_no": attempt_no,
            "state": result.state,
            "reason_code": result.reason_code,
            "remote_receipt_id": result.remote_receipt_id,
            "report_sha256": str(plan.report.content_sha256),
        }
        content = (
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        artifact = self._app.artifacts.publish(
            content,
            media_type="application/json",
            context=CommandContext(
                self._response_key(plan, attempt_no),
                ActorType.WORKER,
                "daily-report-delivery",
                "RECORD_DELIVERY_ATTEMPT",
            ),
        )
        return (
            ArtifactBinding(
                artifact.artifact_id,
                artifact.content_sha256,
                artifact.size_bytes,
            ),
            value,
        )

    def _attempt_response(
        self, plan: DailyDeliveryPlan, trace: RunTrace
    ) -> dict[str, object] | None:
        attempt_no = len(trace.steps[0].attempt_states)
        stored = self._reads.published_artifact(
            self._response_key(plan, attempt_no)
        )
        if stored is None:
            return None
        _binding, content = stored
        value = json.loads(content)
        if (
            not isinstance(value, dict)
            or set(value)
            != {
                "schema",
                "prediction_id",
                "delivery_run_id",
                "channel",
                "attempt_no",
                "state",
                "reason_code",
                "remote_receipt_id",
                "report_sha256",
            }
            or
            value.get("schema") != "daily-report-delivery-attempt-v1"
            or value.get("prediction_id") != str(plan.prediction_id)
            or value.get("delivery_run_id") != str(plan.run_id)
            or value.get("channel") != plan.channel
            or value.get("attempt_no") != attempt_no
            or value.get("report_sha256") != str(plan.report.content_sha256)
        ):
            raise ArtifactIntegrityError("daily delivery response identity changed")
        try:
            DailyDeliveryAttempt(
                state=value["state"],
                reason_code=value["reason_code"],
                remote_receipt_id=value["remote_receipt_id"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactIntegrityError(
                "daily delivery response fact is invalid"
            ) from exc
        return value

    def _status(
        self,
        plan: DailyDeliveryPlan,
        state: str,
        *,
        response: dict[str, object] | None = None,
    ) -> dict[str, object]:
        trace = self._app.runtime.inspect_run(plan.run_id)
        attempt_count = len(trace.steps[0].attempt_states)
        return {
            "state": state,
            "prediction_id": plan.prediction_id,
            "model_version_id": plan.model_version_id,
            "channel": plan.channel,
            "report_artifact_id": plan.report.artifact_id,
            "delivery_run_id": plan.run_id,
            "runtime_state": trace.run_state,
            "attempt_count": attempt_count,
            "expires_at": plan.expires_at,
            "response": response,
            "delivery_attempted": attempt_count > 0,
            "prediction_and_settlement_blocked": False,
        }

    @staticmethod
    def _response_key(plan: DailyDeliveryPlan, attempt_no: int) -> str:
        return (
            "daily-delivery:"
            + str(plan.run_id)
            + ":attempt:"
            + str(attempt_no)
            + ":result"
        )

    @staticmethod
    def _context(plan: DailyDeliveryPlan, key: str) -> CommandContext:
        return CommandContext(
            "daily-delivery:" + str(plan.run_id) + ":" + key,
            ActorType.WORKER,
            "daily-report-delivery",
            "DAILY_REPORT_DELIVERY",
        )


__all__ = [
    "DailyDeliveryAdapter",
    "DailyDeliveryAttempt",
    "DailyDeliveryPlan",
    "DailyReportDelivery",
    "LegacyNotifierDeliveryAdapter",
]
