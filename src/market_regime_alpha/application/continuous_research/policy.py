"""Additive all-day and 14:30--14:55 Continuous Research time policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)


CONTINUOUS_DECISION_WINDOW_POLICY_SCHEMA = "continuous-decision-window-policy-v1"


class ContinuousSessionPhase(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    MORNING_SESSION = "MORNING_SESSION"
    MIDDAY_RECESS = "MIDDAY_RECESS"
    AFTERNOON_SESSION = "AFTERNOON_SESSION"
    DECISION_WINDOW = "DECISION_WINDOW"
    MARKET_CLOSED = "MARKET_CLOSED"


class ContinuousRunState(str, Enum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    MONITORING = "MONITORING"
    WAITING_FOR_NEW_DATA = "WAITING_FOR_NEW_DATA"
    RECOMPUTING = "RECOMPUTING"
    DECISION_WINDOW_OPEN = "DECISION_WINDOW_OPEN"
    MARKET_CLOSED = "MARKET_CLOSED"
    ARCHIVED = "ARCHIVED"
    DATA_BLOCKED = "DATA_BLOCKED"
    DEGRADED = "DEGRADED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ContinuousDecisionWindowAssessment:
    trading_date: date
    observed_at: datetime
    session_phase: ContinuousSessionPhase
    run_state: ContinuousRunState
    decision_window_open: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContinuousDecisionWindowPolicy:
    schema_version: str
    policy_id: ArtifactId
    content_hash: str
    policy_version: str
    timezone_name: str
    market_open: time
    midday_start: time
    midday_end: time
    decision_window_open: time
    decision_window_close: time
    market_close: time
    polling_interval_seconds: int
    provider_timeout_seconds: int
    provider_max_attempts: int
    retry_backoff_seconds: int
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_DECISION_WINDOW_POLICY_SCHEMA:
            raise ValueError("unsupported Continuous decision-window policy schema")
        require_sha256("content_hash", self.content_hash)
        require_text("policy_version", self.policy_version)
        ZoneInfo(self.timezone_name)
        for label, wall_time in (
            ("market_open", self.market_open),
            ("midday_start", self.midday_start),
            ("midday_end", self.midday_end),
            ("decision_window_open", self.decision_window_open),
            ("decision_window_close", self.decision_window_close),
            ("market_close", self.market_close),
        ):
            if (
                not isinstance(wall_time, time)
                or wall_time.tzinfo is not None
                or wall_time.microsecond
            ):
                raise ValueError(f"{label} must be a naive whole-second wall time")
        if not (
            self.market_open
            < self.midday_start
            < self.midday_end
            < self.decision_window_open
            <= self.decision_window_close
            < self.market_close
        ):
            raise ValueError("Continuous session times are not monotonic")
        for label, numeric_value in (
            ("polling_interval_seconds", self.polling_interval_seconds),
            ("provider_timeout_seconds", self.provider_timeout_seconds),
            ("provider_max_attempts", self.provider_max_attempts),
        ):
            if (
                isinstance(numeric_value, bool)
                or not isinstance(numeric_value, int)
                or numeric_value <= 0
            ):
                raise ValueError(f"{label} must be a positive integer")
        if (
            isinstance(self.retry_backoff_seconds, bool)
            or not isinstance(self.retry_backoff_seconds, int)
            or self.retry_backoff_seconds < 0
        ):
            raise ValueError("retry_backoff_seconds must be a non-negative integer")
        require_unique_text("policy limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("policy limitations must be sorted")
        for required in (
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ):
            if required not in self.limitations:
                raise ValueError("Continuous policy authority ceiling is incomplete")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        timezone_name: str,
        market_open: time,
        midday_start: time,
        midday_end: time,
        decision_window_open: time,
        decision_window_close: time,
        market_close: time,
        polling_interval_seconds: int,
        provider_timeout_seconds: int,
        provider_max_attempts: int,
        retry_backoff_seconds: int,
        limitations: tuple[str, ...],
    ) -> ContinuousDecisionWindowPolicy:
        values: dict[str, Any] = {
            "policy_version": policy_version,
            "timezone_name": timezone_name,
            "market_open": market_open,
            "midday_start": midday_start,
            "midday_end": midday_end,
            "decision_window_open": decision_window_open,
            "decision_window_close": decision_window_close,
            "market_close": market_close,
            "polling_interval_seconds": polling_interval_seconds,
            "provider_timeout_seconds": provider_timeout_seconds,
            "provider_max_attempts": provider_max_attempts,
            "retry_backoff_seconds": retry_backoff_seconds,
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_policy_payload(**values))
        return cls(
            schema_version=CONTINUOUS_DECISION_WINDOW_POLICY_SCHEMA,
            policy_id=ArtifactId(
                f"continuous-policy-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _policy_payload(
            policy_version=self.policy_version,
            timezone_name=self.timezone_name,
            market_open=self.market_open,
            midday_start=self.midday_start,
            midday_end=self.midday_end,
            decision_window_open=self.decision_window_open,
            decision_window_close=self.decision_window_close,
            market_close=self.market_close,
            polling_interval_seconds=self.polling_interval_seconds,
            provider_timeout_seconds=self.provider_timeout_seconds,
            provider_max_attempts=self.provider_max_attempts,
            retry_backoff_seconds=self.retry_backoff_seconds,
            limitations=self.limitations,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Continuous decision-window policy hash mismatch")
        expected = f"continuous-policy-{digest.split(':', 1)[1][:24]}"
        if str(self.policy_id) != expected:
            raise ValueError("Continuous decision-window policy identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ContinuousDecisionWindowPolicy:
        expected = {"policy_id", "content_hash", *_policy_payload_keys()}
        if set(payload) != expected:
            raise ValueError("Continuous decision-window policy fields mismatch")
        result = cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            content_hash=str(payload["content_hash"]),
            policy_version=str(payload["policy_version"]),
            timezone_name=str(payload["timezone_name"]),
            market_open=time.fromisoformat(str(payload["market_open"])),
            midday_start=time.fromisoformat(str(payload["midday_start"])),
            midday_end=time.fromisoformat(str(payload["midday_end"])),
            decision_window_open=time.fromisoformat(
                str(payload["decision_window_open"])
            ),
            decision_window_close=time.fromisoformat(
                str(payload["decision_window_close"])
            ),
            market_close=time.fromisoformat(str(payload["market_close"])),
            polling_interval_seconds=int(payload["polling_interval_seconds"]),
            provider_timeout_seconds=int(payload["provider_timeout_seconds"]),
            provider_max_attempts=int(payload["provider_max_attempts"]),
            retry_backoff_seconds=int(payload["retry_backoff_seconds"]),
            limitations=_strings(payload["limitations"], "limitations"),
        )
        result.verify_identity()
        return result

    def assess(
        self,
        *,
        trading_date: date,
        observed_at: datetime,
    ) -> ContinuousDecisionWindowAssessment:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        local = observed_at.astimezone(ZoneInfo(self.timezone_name))
        if local.date() != trading_date:
            raise ValueError("observed_at local date must match trading_date")
        wall = local.timetz().replace(tzinfo=None)
        if wall < self.market_open:
            phase = ContinuousSessionPhase.PRE_MARKET
            state = ContinuousRunState.PREPARING
        elif wall < self.midday_start:
            phase = ContinuousSessionPhase.MORNING_SESSION
            state = ContinuousRunState.MONITORING
        elif wall < self.midday_end:
            phase = ContinuousSessionPhase.MIDDAY_RECESS
            state = ContinuousRunState.WAITING_FOR_NEW_DATA
        elif self.decision_window_open <= wall <= self.decision_window_close:
            phase = ContinuousSessionPhase.DECISION_WINDOW
            state = ContinuousRunState.DECISION_WINDOW_OPEN
        elif wall < self.market_close:
            phase = ContinuousSessionPhase.AFTERNOON_SESSION
            state = ContinuousRunState.MONITORING
        else:
            phase = ContinuousSessionPhase.MARKET_CLOSED
            state = ContinuousRunState.MARKET_CLOSED
        window_open = phase is ContinuousSessionPhase.DECISION_WINDOW
        reasons = (
            ("DECISION_WINDOW_OPEN", "EXACT_1455_TICK_NOT_REQUIRED")
            if window_open
            else (f"SESSION_{phase.value}",)
        )
        return ContinuousDecisionWindowAssessment(
            trading_date=trading_date,
            observed_at=observed_at,
            session_phase=phase,
            run_state=state,
            decision_window_open=window_open,
            reason_codes=reasons,
        )

    def next_tick_after(
        self,
        *,
        trading_date: date,
        observed_at: datetime,
    ) -> datetime | None:
        assessment = self.assess(
            trading_date=trading_date,
            observed_at=observed_at,
        )
        if assessment.session_phase is ContinuousSessionPhase.MARKET_CLOSED:
            return None
        zone = ZoneInfo(self.timezone_name)
        local = observed_at.astimezone(zone)
        candidate = local + timedelta(seconds=self.polling_interval_seconds)
        close = datetime.combine(trading_date, self.market_close, tzinfo=zone)
        if candidate >= close:
            candidate = close
        return candidate.astimezone(observed_at.tzinfo)


def default_continuous_decision_window_policy() -> ContinuousDecisionWindowPolicy:
    return ContinuousDecisionWindowPolicy.create(
        policy_version="continuous-research-a-share-v1",
        timezone_name="Asia/Shanghai",
        market_open=time(9, 30),
        midday_start=time(11, 30),
        midday_end=time(13, 0),
        decision_window_open=time(14, 30),
        decision_window_close=time(14, 55),
        market_close=time(15, 0),
        polling_interval_seconds=60,
        provider_timeout_seconds=3,
        provider_max_attempts=2,
        retry_backoff_seconds=1,
        limitations=(
            "EXACT_1455_TICK_NOT_REQUIRED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _policy_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CONTINUOUS_DECISION_WINDOW_POLICY_SCHEMA,
        "policy_version": values["policy_version"],
        "timezone_name": values["timezone_name"],
        "market_open": values["market_open"].isoformat(),
        "midday_start": values["midday_start"].isoformat(),
        "midday_end": values["midday_end"].isoformat(),
        "decision_window_open": values["decision_window_open"].isoformat(),
        "decision_window_close": values["decision_window_close"].isoformat(),
        "market_close": values["market_close"].isoformat(),
        "polling_interval_seconds": values["polling_interval_seconds"],
        "provider_timeout_seconds": values["provider_timeout_seconds"],
        "provider_max_attempts": values["provider_max_attempts"],
        "retry_backoff_seconds": values["retry_backoff_seconds"],
        "limitations": list(values["limitations"]),
    }


def _policy_payload_keys() -> set[str]:
    return {
        "schema_version",
        "policy_version",
        "timezone_name",
        "market_open",
        "midday_start",
        "midday_end",
        "decision_window_open",
        "decision_window_close",
        "market_close",
        "polling_interval_seconds",
        "provider_timeout_seconds",
        "provider_max_attempts",
        "retry_backoff_seconds",
        "limitations",
    }


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


__all__ = [
    "CONTINUOUS_DECISION_WINDOW_POLICY_SCHEMA",
    "ContinuousDecisionWindowAssessment",
    "ContinuousDecisionWindowPolicy",
    "ContinuousRunState",
    "ContinuousSessionPhase",
    "default_continuous_decision_window_policy",
]
