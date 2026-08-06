"""Durable, bounded scheduling control for the sole Continuous Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Mapping

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousDecisionWindowPolicy,
)
from market_regime_alpha.application.continuous_research.ports import (
    ProviderAcquisitionRequest,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
    ContinuousTickExecutionResult,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.market_data.contracts import require_utc_second


class ContinuousScheduleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class TradingDayAssessment:
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    trading_date: date
    is_trading_day: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date):
            raise TypeError("trading_date must be a date")
        require_sha256("trading_calendar_hash", self.trading_calendar_hash)
        if not isinstance(self.is_trading_day, bool):
            raise TypeError("is_trading_day must be bool")
        if not self.reason_codes or self.reason_codes != tuple(
            sorted(set(self.reason_codes))
        ):
            raise ValueError("Trading Day reasons must be non-empty, unique, and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "trading_calendar_id": str(self.trading_calendar_id),
            "trading_calendar_hash": self.trading_calendar_hash,
            "trading_date": self.trading_date.isoformat(),
            "is_trading_day": self.is_trading_day,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TradingDayAssessment:
        expected = {
            "trading_calendar_id",
            "trading_calendar_hash",
            "trading_date",
            "is_trading_day",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("Trading Day assessment fields mismatch")
        reasons = payload["reason_codes"]
        if not isinstance(reasons, list) or any(
            not isinstance(item, str) for item in reasons
        ):
            raise ValueError("Trading Day reasons must be a string array")
        is_trading_day = payload["is_trading_day"]
        if not isinstance(is_trading_day, bool):
            raise ValueError("is_trading_day must be bool")
        return cls(
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            is_trading_day=is_trading_day,
            reason_codes=tuple(reasons),
        )


@dataclass(frozen=True, slots=True)
class ContinuousScheduleSnapshot:
    schedule_id: ArtifactId
    schedule_hash: str
    run_id: ArtifactId
    status: ContinuousScheduleStatus
    next_tick_at: datetime | None
    last_reserved_tick_id: ArtifactId | None
    last_reserved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": str(self.schedule_id),
            "schedule_hash": self.schedule_hash,
            "run_id": str(self.run_id),
            "status": self.status.value,
            "next_tick_at": (
                None if self.next_tick_at is None else self.next_tick_at.isoformat()
            ),
            "last_reserved_tick_id": (
                None
                if self.last_reserved_tick_id is None
                else str(self.last_reserved_tick_id)
            ),
            "last_reserved_at": (
                None
                if self.last_reserved_at is None
                else self.last_reserved_at.isoformat()
            ),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": None if self.closed_at is None else self.closed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ContinuousScheduleRunResult:
    status: str
    schedule: ContinuousScheduleSnapshot
    tick_result: ContinuousTickExecutionResult | None
    reason_codes: tuple[str, ...]

    @property
    def entry_authority_granted(self) -> bool:
        return False


ProviderRequestBuilder = Callable[
    [ContinuousResearchCommand, RuntimeTickCommand], ProviderAcquisitionRequest
]


class ContinuousResearchScheduleRunner:
    """Runs at most one due/recoverable Tick; PostgreSQL owns the schedule."""

    def __init__(
        self,
        *,
        journal: PostgresContinuousResearchJournal,
        tick_runner: ContinuousResearchTickRunner,
        policy: ContinuousDecisionWindowPolicy,
        provider_request_builder: ProviderRequestBuilder,
    ) -> None:
        if not isinstance(journal, PostgresContinuousResearchJournal):
            raise TypeError("journal must be PostgresContinuousResearchJournal")
        if not isinstance(tick_runner, ContinuousResearchTickRunner):
            raise TypeError("tick_runner must be ContinuousResearchTickRunner")
        if not isinstance(policy, ContinuousDecisionWindowPolicy):
            raise TypeError("policy must be ContinuousDecisionWindowPolicy")
        if not callable(provider_request_builder):
            raise TypeError("provider_request_builder must be callable")
        self._journal = journal
        self._tick_runner = tick_runner
        self._policy = policy
        self._provider_request_builder = provider_request_builder

    def run_due_once(
        self,
        *,
        run_command: ContinuousResearchCommand,
        trading_day: TradingDayAssessment,
        now: datetime,
    ) -> ContinuousScheduleRunResult:
        require_utc_second("now", now)
        _validate_trading_day(run_command, trading_day)
        self._journal.create_or_get(run_command)
        schedule = self._journal.initialize_schedule(
            run_command=run_command,
            policy=self._policy,
            trading_day=trading_day,
            initial_tick_at=now,
        )
        if schedule.status is ContinuousScheduleStatus.NON_TRADING_DAY:
            return ContinuousScheduleRunResult(
                status="NON_TRADING_DAY",
                schedule=schedule,
                tick_result=None,
                reason_codes=("ENTRY_BLOCKED", "NON_TRADING_DAY"),
            )
        tick = self._journal.get_recoverable_tick(run_command.run_id, now=now)
        if tick is None:
            reserved = self._journal.reserve_due_tick(
                run_command=run_command,
                policy=self._policy,
                now=now,
            )
            if reserved is None:
                return ContinuousScheduleRunResult(
                    status="NOT_DUE",
                    schedule=self._journal.get_schedule(run_command.run_id),
                    tick_result=None,
                    reason_codes=("ENTRY_BLOCKED", "NEXT_TICK_NOT_DUE"),
                )
            tick = reserved
        request = self._provider_request_builder(run_command, tick.command)
        result = self._tick_runner.execute(
            run_command=run_command,
            tick_command=tick.command,
            provider_request=request,
        )
        schedule = self._journal.get_schedule(run_command.run_id)
        return ContinuousScheduleRunResult(
            status=result.tick.status.value,
            schedule=schedule,
            tick_result=result,
            reason_codes=result.reason_codes,
        )


def schedule_identity(
    *,
    run_command: ContinuousResearchCommand,
    policy: ContinuousDecisionWindowPolicy,
    trading_day: TradingDayAssessment,
) -> tuple[ArtifactId, str]:
    digest = canonical_hash(
        {
            "schema_version": "continuous-runtime-schedule-v1",
            "run_id": str(run_command.run_id),
            "command_hash": run_command.command_hash,
            "policy_id": str(policy.policy_id),
            "policy_hash": policy.content_hash,
            "trading_calendar_id": str(trading_day.trading_calendar_id),
            "trading_calendar_hash": trading_day.trading_calendar_hash,
            "trading_date": run_command.trading_date.isoformat(),
            "is_trading_day": trading_day.is_trading_day,
        }
    )
    return (
        ArtifactId(f"continuous-schedule-{digest.split(':', 1)[1][:24]}"),
        digest,
    )


def _validate_trading_day(
    run_command: ContinuousResearchCommand,
    trading_day: TradingDayAssessment,
) -> None:
    if (
        trading_day.trading_date != run_command.trading_date
        or trading_day.trading_calendar_id != run_command.trading_calendar_id
        or trading_day.trading_calendar_hash != run_command.trading_calendar_hash
    ):
        raise ValueError("Trading Day assessment does not match the run command")


__all__ = [
    "ContinuousResearchScheduleRunner",
    "ContinuousScheduleRunResult",
    "ContinuousScheduleSnapshot",
    "ContinuousScheduleStatus",
    "TradingDayAssessment",
    "schedule_identity",
]
