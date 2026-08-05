"""Read-only deterministic integrity replay for Continuous Research lineage."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


@dataclass(frozen=True, slots=True)
class ContinuousResearchReplayResult:
    run_id: ArtifactId
    replay_hash: str
    tick_count: int
    evidence_count: int
    decision_count: int
    child_reference_count: int
    receipt_count: int
    integrity_status: str
    limitations: tuple[str, ...]

    @property
    def entry_authority_granted(self) -> bool:
        return False

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "schema_version": "continuous-research-replay-result-v1",
            "run_id": str(self.run_id),
            "replay_hash": self.replay_hash,
            "tick_count": self.tick_count,
            "evidence_count": self.evidence_count,
            "decision_count": self.decision_count,
            "child_reference_count": self.child_reference_count,
            "receipt_count": self.receipt_count,
            "integrity_status": self.integrity_status,
            "limitations": list(self.limitations),
            "entry_authority_granted": False,
        }


def replay_continuous_research(
    journal: PostgresContinuousResearchJournal, run_id: ArtifactId
) -> ContinuousResearchReplayResult:
    snapshot = journal.get_run(run_id)
    snapshot.command.verify_identity()
    evidence_hashes: list[str] = []
    decision_hashes: list[str] = []
    child_hashes: list[str] = []
    receipt_hashes: list[str] = []
    for tick in snapshot.ticks:
        tick.command.verify_identity()
        if tick.evidence_commit_id is not None:
            evidence = journal.get_evidence_commit(tick.evidence_commit_id)
            evidence.verify_identity()
            evidence_hashes.append(evidence.commit_hash)
        if tick.change_decision_id is not None:
            decision = journal.get_change_decision(tick.change_decision_id)
            decision.verify_identity()
            decision_hashes.append(decision.decision_hash)
        for child in journal.get_child_references(
            snapshot.command.run_id, tick.command.tick_id
        ):
            child.verify_identity()
            child_hashes.append(child.reference_hash)
        if tick.receipt is not None:
            tick.receipt.verify_identity()
            receipt_hashes.append(tick.receipt.receipt_hash)
    payload = {
        "schema_version": "continuous-research-replay-v1",
        "run_command_hash": snapshot.command.command_hash,
        "tick_hashes": [item.command.tick_hash for item in snapshot.ticks],
        "evidence_hashes": evidence_hashes,
        "decision_hashes": decision_hashes,
        "child_reference_hashes": child_hashes,
        "receipt_hashes": receipt_hashes,
        "event_ids": [item.event_id for item in snapshot.events],
    }
    return ContinuousResearchReplayResult(
        run_id=snapshot.command.run_id,
        replay_hash=canonical_hash(payload),
        tick_count=len(snapshot.ticks),
        evidence_count=len(evidence_hashes),
        decision_count=len(decision_hashes),
        child_reference_count=len(child_hashes),
        receipt_count=len(receipt_hashes),
        integrity_status="VERIFIED",
        limitations=(
            "ENTRY_BLOCKED",
            "REPLAY_DOES_NOT_QUALIFY_PROVIDER_OR_ALPHA",
        ),
    )


__all__ = ["ContinuousResearchReplayResult", "replay_continuous_research"]
