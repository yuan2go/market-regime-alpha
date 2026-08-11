"""Canonical source-freeze service over the retained Daily identity adapter.

The legacy DailyLoop remains a compatibility consumer/adapter.  Canonical
Free-Data composition depends only on this source-only contract and cannot call
the legacy research/finalization path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from market_regime_alpha.application.daily_loop.commands import DailyRunCommand
from market_regime_alpha.application.daily_loop.repositories import (
    AcquisitionStageReceipt,
    DailyRunRecord,
    DailyRunRepository,
)
from market_regime_alpha.application.daily_loop.runner import DailyLoopRunner
from market_regime_alpha.data.providers.public_composite import (
    AcquiredReplaySource,
    PublicCompositeLiveProfile,
)
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.universe.daily_exploratory import DailyUniversePolicy


Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class SourceFreezeResult:
    record: DailyRunRecord
    source_archive_path: Path
    acquired: AcquiredReplaySource


class SourceFreezeExecutor(Protocol):
    def prepare_history(self, command: DailyRunCommand) -> AcquisitionStageReceipt: ...

    def freeze_security_status(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt: ...

    def freeze_supplemental(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt: ...

    def freeze_decision_quote(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt: ...

    def freeze_sources(
        self,
        command: DailyRunCommand,
        *,
        replay_archive_path: Path | None = None,
    ) -> SourceFreezeExecutorResult: ...


class SourceFreezeExecutorResult(Protocol):
    record: DailyRunRecord
    source_archive_path: Path
    acquired: AcquiredReplaySource


class SourceFreezeService:
    """Narrow source-only API; no Daily research/finalization operation exists."""

    def __init__(self, executor: SourceFreezeExecutor) -> None:
        self._executor = executor

    def prepare_history(self, command: DailyRunCommand) -> AcquisitionStageReceipt:
        return self._executor.prepare_history(command)

    def freeze_security_status(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt:
        return self._executor.freeze_security_status(command)

    def freeze_supplemental(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt:
        return self._executor.freeze_supplemental(command)

    def freeze_decision_quote(
        self, command: DailyRunCommand
    ) -> AcquisitionStageReceipt:
        return self._executor.freeze_decision_quote(command)

    def freeze(
        self,
        command: DailyRunCommand,
        *,
        replay_archive_path: Path | None = None,
    ) -> SourceFreezeResult:
        raw = self._executor.freeze_sources(
            command, replay_archive_path=replay_archive_path
        )
        return SourceFreezeResult(
            record=raw.record,
            source_archive_path=raw.source_archive_path,
            acquired=raw.acquired,
        )


def compose_daily_source_freeze(
    *,
    repository: DailyRunRepository,
    code_revision: str,
    live_profile: PublicCompositeLiveProfile | None,
    policy: DailyUniversePolicy,
    clock: Clock,
    model_selector: PostgresModelGovernanceRepository | None = None,
) -> SourceFreezeService:
    """Retain historical Daily identities behind the canonical source seam."""

    adapter = DailyLoopRunner(
        repository=repository,
        code_revision=code_revision,
        live_profile=live_profile,
        policy=policy,
        clock=clock,
        model_selector=model_selector,
    )
    return SourceFreezeService(adapter)
