"""Recoverable exploratory daily-loop runtime kernel."""

from typing import TYPE_CHECKING, Any

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    DailyRunId,
    DailyRunIdentity,
    RunMode,
    RunRequestId,
)
from market_regime_alpha.application.daily_loop.repositories import (
    DailyRunRecord,
    DailyRunRepository,
    StageReceipt,
)
from market_regime_alpha.application.daily_loop.sqlite_repository import (
    SQLiteDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.state import DailyRunStatus

if TYPE_CHECKING:
    from market_regime_alpha.application.daily_loop.runner import (
        DailyLoopRunner,
        DailyLoopRunResult,
        DailyLoopSourceFreezeResult,
        DailyLoopSettlementResult,
    )

__all__ = [
    "DailyRunCommand",
    "DailyLoopRunResult",
    "DailyLoopRunner",
    "DailyLoopSourceFreezeResult",
    "DailyLoopSettlementResult",
    "DailyRunId",
    "DailyRunIdentity",
    "DailyRunRecord",
    "DailyRunRepository",
    "DailyRunStatus",
    "RunMode",
    "RunRequestId",
    "PostgresDailyRunRepository",
    "SQLiteDailyRunRepository",
    "StageReceipt",
    "DAILY_B0_B1_MODEL_SET_ID",
]


def __getattr__(name: str) -> Any:
    if name in {
        "DAILY_B0_B1_MODEL_SET_ID",
        "DailyLoopRunner",
        "DailyLoopRunResult",
        "DailyLoopSourceFreezeResult",
        "DailyLoopSettlementResult",
    }:
        from market_regime_alpha.application.daily_loop import runner

        return getattr(runner, name)
    raise AttributeError(name)
