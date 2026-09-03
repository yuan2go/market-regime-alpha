"""Generic read-only Backtest replay and Artifact byte reconciliation."""

from __future__ import annotations

import hashlib
from uuid import UUID

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
    ) -> None:
        self._authorities = authorities
        self._artifact_bytes = artifact_bytes

    def verify(self, exploratory_backtest_run_id: UUID) -> BacktestReplayVerification:
        snapshot = self._authorities.load(exploratory_backtest_run_id)
        mismatches: list[str] = []
        for binding in snapshot.artifact_bindings:
            content = self._artifact_bytes.read_bytes(
                str(binding.content_sha256), expected_size=binding.size_bytes
            )
            if hashlib.sha256(content).hexdigest() != str(binding.content_sha256):
                mismatches.append(f"ARTIFACT_BYTES:{binding.artifact_id}")
        return BacktestReplayVerification(
            exploratory_backtest_run_id=exploratory_backtest_run_id,
            matched=not mismatches,
            mismatch_codes=tuple(mismatches),
            source=snapshot.run.source.value,
            definition_sha256=str(snapshot.run.definition_sha256),
        )


__all__ = ["BacktestReplayApplication"]
