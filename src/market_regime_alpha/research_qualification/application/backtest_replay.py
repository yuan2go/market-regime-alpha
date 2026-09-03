"""Generic read-only Backtest replay and Artifact byte reconciliation."""

from __future__ import annotations

import hashlib
from uuid import UUID

from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestExecutionState,
)
from market_regime_alpha.research_qualification.ports.backtest_execution import (
    BacktestExecutionObservationPort,
)
from market_regime_alpha.research_qualification.ports.backtest_queries import (
    BacktestArtifactByteReader,
    BacktestAuthorityQueryPort,
    BacktestReplayVerification,
)


class BacktestReplayApplication:
    """Verify a projection without mutating any canonical owner."""

    def __init__(
        self,
        authorities: BacktestAuthorityQueryPort,
        artifact_bytes: BacktestArtifactByteReader,
        execution_observations: BacktestExecutionObservationPort | None = None,
    ) -> None:
        self._authorities = authorities
        self._artifact_bytes = artifact_bytes
        self._execution_observations = execution_observations

    def verify(self, exploratory_backtest_run_id: UUID) -> BacktestReplayVerification:
        snapshot = self._authorities.load(exploratory_backtest_run_id)
        mismatches: list[str] = []
        for binding in snapshot.artifact_bindings:
            content = self._artifact_bytes.read_bytes(
                str(binding.content_sha256), expected_size=binding.size_bytes
            )
            if hashlib.sha256(content).hexdigest() != str(binding.content_sha256):
                mismatches.append(f"ARTIFACT_BYTES:{binding.artifact_id}")
        if self._execution_observations is not None:
            expected = BacktestExecutionPlanner().compile(snapshot.run)
            observations = self._execution_observations.observe(
                snapshot.run, expected.expected_actions
            )
            execution = BacktestExecutionPlanner().compile(
                snapshot.run, observations
            )
            if execution.execution_state is not BacktestExecutionState.COMPLETED:
                mismatches.append(
                    f"EXECUTION:{execution.execution_state.value}"
                )
            if execution.integrity_mismatch_action_ids:
                mismatches.extend(
                    f"ACTION_INTEGRITY:{action_id}"
                    for action_id in execution.integrity_mismatch_action_ids
                )
        return BacktestReplayVerification(
            exploratory_backtest_run_id=exploratory_backtest_run_id,
            matched=not mismatches,
            mismatch_codes=tuple(mismatches),
            source=snapshot.run.source.value,
            definition_sha256=str(snapshot.run.definition_sha256),
        )


__all__ = ["BacktestReplayApplication"]
