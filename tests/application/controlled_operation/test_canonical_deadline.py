from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleStageName,
)
from tests.postgres_path_repositories import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.controlled_operation.canonical_bridge import (
    ControlledCanonicalDeadlineExceeded,
    _TimedStageHandler,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageStatus,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledDecisionTimeOperationRunner,
)
from tests.postgres_path_repositories import (
    PostgresDecisionTimeOperationJournal,
    controlled_runner_dependencies,
)
from market_regime_alpha.core.identity import ArtifactId


UTC = timezone.utc


class _CrossCutoffHandler:
    stage_name = LifecycleStageName.SIGNAL
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, current_time: list[datetime], hard_cutoff: datetime) -> None:
        self._current_time = current_time
        self._hard_cutoff = hard_cutoff
        self.calls = 0

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        del context
        self.calls += 1
        self._current_time[0] = self._hard_cutoff + timedelta(seconds=1)
        return cast(StageExecutionResult, object())


def test_timed_canonical_stage_stops_when_handler_crosses_hard_cutoff() -> None:
    hard_cutoff = datetime(2026, 8, 5, 6, 56, tzinfo=UTC)
    current_time = [hard_cutoff - timedelta(seconds=1)]
    handler = _CrossCutoffHandler(current_time, hard_cutoff)
    timed = _TimedStageHandler(
        handler,
        {},
        clock=lambda: current_time[0],
        hard_cutoff=hard_cutoff,
    )

    with pytest.raises(
        ControlledCanonicalDeadlineExceeded,
        match="HARD_CUTOFF_EXCEEDED",
    ):
        timed.execute(cast(LifecycleStageContext, object()))

    assert handler.calls == 1


def test_timed_canonical_stage_rejects_work_that_starts_after_cutoff() -> None:
    hard_cutoff = datetime(2026, 8, 5, 6, 56, tzinfo=UTC)
    current_time = [hard_cutoff + timedelta(seconds=1)]
    handler = _CrossCutoffHandler(current_time, hard_cutoff)
    timed = _TimedStageHandler(
        handler,
        {},
        clock=lambda: current_time[0],
        hard_cutoff=hard_cutoff,
    )

    with pytest.raises(ControlledCanonicalDeadlineExceeded):
        timed.execute(cast(LifecycleStageContext, object()))

    assert handler.calls == 0


def test_resume_admission_rejects_migrated_database_without_child_run(
    tmp_path: Path,
) -> None:
    decision_time = datetime(2026, 8, 5, 6, 55, tzinfo=UTC)
    digest = "sha256:" + "1" * 64
    command = ControlledOperationCommand.create(
        idempotency_key="empty-canonical-child",
        decision_date=decision_time.date(),
        decision_time=decision_time,
        policy_id=ArtifactId("policy"),
        policy_hash=digest,
        trading_calendar_id=ArtifactId("calendar"),
        trading_calendar_hash=digest,
        configuration_manifest_id=ArtifactId("config"),
        configuration_manifest_hash=digest,
        model_manifest_id=ArtifactId("model"),
        model_manifest_hash=digest,
        code_revision="fixture",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    completed_names = {
        DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
        DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
        DecisionTimeOperationStageName.DAILY_DATASET,
        DecisionTimeOperationStageName.STATIC_FEATURES,
        DecisionTimeOperationStageName.OPERATIONAL_RESEARCH,
        DecisionTimeOperationStageName.CANDIDATE_SET,
        DecisionTimeOperationStageName.CANDIDATE_MINUTE_ACQUISITION,
        DecisionTimeOperationStageName.INTRADAY_DATASET,
        DecisionTimeOperationStageName.INTRADAY_FEATURE_OVERLAY,
    }
    snapshot = SimpleNamespace(
        status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
        stages=tuple(
            SimpleNamespace(
                stage_name=stage,
                status=(
                    DecisionTimeOperationStageStatus.COMPLETED
                    if stage in completed_names
                    else DecisionTimeOperationStageStatus.PENDING
                ),
                receipt=None,
            )
            for stage in DecisionTimeOperationStageName
        ),
    )
    journal = SimpleNamespace(get=lambda _run_id: snapshot)
    output_root = tmp_path / "operations"
    database_path = output_root / str(command.run_id) / "canonical-lifecycle.postgres-scope"
    PostgresLifecycleRunRepository(database_path)
    runner = ControlledDecisionTimeOperationRunner(
        journal=cast(PostgresDecisionTimeOperationJournal, journal),
        output_root=output_root,
        clock=lambda: decision_time + timedelta(seconds=10),
        **controlled_runner_dependencies(
            database_path,
            clock=lambda: decision_time + timedelta(seconds=10),
        ),
    )

    assert not runner._canonical_child_was_admitted(
        command=command,
        observed_at=decision_time + timedelta(seconds=10),
        hard_cutoff=decision_time + timedelta(minutes=1),
    )
