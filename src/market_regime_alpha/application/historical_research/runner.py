"""Chronological Historical Research runner over the shared session kernel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunSnapshot,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


@dataclass(frozen=True, slots=True)
class HistoricalReplayMismatch:
    trading_date: str
    stage: ResearchSessionStage
    expected_receipt_hash: str
    actual_receipt_hash: str

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "trading_date": self.trading_date,
            "stage": self.stage.value,
            "expected_receipt_hash": self.expected_receipt_hash,
            "actual_receipt_hash": self.actual_receipt_hash,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayReport:
    report_id: ArtifactId
    report_hash: str
    run_id: ArtifactId
    command_hash: str
    matched: bool
    replayed_session_count: int
    mismatches: tuple[HistoricalReplayMismatch, ...]
    schema_version: str = "historical-replay-report/v1"

    def __post_init__(self) -> None:
        if self.matched is bool(self.mismatches):
            raise ValueError("Historical replay match status contradicts mismatches")
        digest = canonical_hash(self.identity_payload())
        if digest != self.report_hash:
            raise ValueError("Historical replay report hash mismatch")
        if str(self.report_id) != f"historical-replay-{digest[7:31]}":
            raise ValueError("Historical replay report identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": str(self.run_id),
            "command_hash": self.command_hash,
            "matched": self.matched,
            "replayed_session_count": self.replayed_session_count,
            "mismatches": [item.to_canonical_dict() for item in self.mismatches],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "report_hash": self.report_hash,
            **self.identity_payload(),
        }


class HistoricalResearchRunner:
    """Apply business stages serially; journal each owner receipt transactionally."""

    def __init__(
        self,
        *,
        journal: PostgresHistoricalResearchJournal,
        kernel: ResearchDecisionSessionKernel,
    ) -> None:
        if not isinstance(journal, PostgresHistoricalResearchJournal):
            raise TypeError("journal must be PostgresHistoricalResearchJournal")
        if not isinstance(kernel, ResearchDecisionSessionKernel):
            raise TypeError("kernel must be ResearchDecisionSessionKernel")
        self._journal = journal
        self._kernel = kernel

    def run(
        self,
        *,
        command: HistoricalResearchCommand,
        max_stage_commits: int | None = None,
    ) -> HistoricalRunSnapshot:
        if max_stage_commits is not None and max_stage_commits <= 0:
            raise ValueError("max_stage_commits must be positive")
        self._journal.create_or_get(command)
        return self._drain(command.run_id, max_stage_commits=max_stage_commits)

    def resume(
        self,
        *,
        run_id: ArtifactId,
        max_stage_commits: int | None = None,
    ) -> HistoricalRunSnapshot:
        if max_stage_commits is not None and max_stage_commits <= 0:
            raise ValueError("max_stage_commits must be positive")
        self._journal.get_run(run_id)
        return self._drain(run_id, max_stage_commits=max_stage_commits)

    def replay(self, *, run_id: ArtifactId) -> HistoricalReplayReport:
        snapshot = self._journal.get_run(run_id)
        mismatches: list[HistoricalReplayMismatch] = []
        for session in snapshot.sessions:
            recomputed = self._kernel.run(request=session.request)
            for expected, actual in zip(session.receipts, recomputed, strict=False):
                if expected.receipt_hash != actual.receipt_hash:
                    mismatches.append(
                        HistoricalReplayMismatch(
                            trading_date=session.request.trading_date.isoformat(),
                            stage=expected.stage,
                            expected_receipt_hash=expected.receipt_hash,
                            actual_receipt_hash=actual.receipt_hash,
                        )
                    )
                    break
            else:
                if len(session.receipts) != len(recomputed):
                    stage = tuple(ResearchSessionStage)[
                        min(len(session.receipts), len(recomputed))
                    ]
                    mismatches.append(
                        HistoricalReplayMismatch(
                            trading_date=session.request.trading_date.isoformat(),
                            stage=stage,
                            expected_receipt_hash=(
                                "MISSING"
                                if len(session.receipts) <= stage.ordinal - 1
                                else session.receipts[stage.ordinal - 1].receipt_hash
                            ),
                            actual_receipt_hash=(
                                "MISSING"
                                if len(recomputed) <= stage.ordinal - 1
                                else recomputed[stage.ordinal - 1].receipt_hash
                            ),
                        )
                    )
        values = {
            "schema_version": "historical-replay-report/v1",
            "run_id": str(run_id),
            "command_hash": snapshot.command.command_hash,
            "matched": not mismatches,
            "replayed_session_count": len(snapshot.sessions),
            "mismatches": [item.to_canonical_dict() for item in mismatches],
        }
        digest = canonical_hash(values)
        return HistoricalReplayReport(
            report_id=ArtifactId(f"historical-replay-{digest[7:31]}"),
            report_hash=digest,
            run_id=run_id,
            command_hash=snapshot.command.command_hash,
            matched=not mismatches,
            replayed_session_count=len(snapshot.sessions),
            mismatches=tuple(mismatches),
        )

    def _drain(
        self,
        run_id: ArtifactId,
        *,
        max_stage_commits: int | None,
    ) -> HistoricalRunSnapshot:
        committed = 0
        while max_stage_commits is None or committed < max_stage_commits:
            claim = self._journal.claim_next(run_id)
            if claim is None:
                break
            run = self._journal.get_run(run_id)
            request = run.command.session_request(claim.trading_date)
            computed = self._kernel.run_next(
                request=request,
                completed_prefix=claim.completed_prefix,
            )
            if len(computed) != len(claim.completed_prefix) + 1:
                raise ValueError("shared session kernel did not compute one claimed stage")
            self._journal.record_stage(claim=claim, receipt=computed[-1])
            committed += 1
        return self._journal.get_run(run_id)


__all__ = [
    "HistoricalReplayMismatch",
    "HistoricalReplayReport",
    "HistoricalResearchRunner",
]
