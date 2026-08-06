"""Deterministic read-only replay of one PostgreSQL Decision Runtime receipt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


@dataclass(frozen=True, slots=True)
class DecisionSystemReplayResult:
    run_id: ArtifactId
    tick_id: ArtifactId
    receipt_id: ArtifactId
    receipt_hash: str
    replay_hash: str
    verified_authority_count: int
    entry_authority_granted: bool = False
    broker_authority_granted: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "tick_id": str(self.tick_id),
            "receipt_id": str(self.receipt_id),
            "receipt_hash": self.receipt_hash,
            "replay_hash": self.replay_hash,
            "verified_authority_count": self.verified_authority_count,
            "entry_authority_granted": False,
            "broker_authority_granted": False,
        }


def replay_decision_system(
    repository: PostgresDecisionSystemRepository,
    *,
    run_id: ArtifactId,
    tick_id: ArtifactId,
) -> DecisionSystemReplayResult:
    receipt = repository.get_runtime_receipt(run_id=run_id, tick_id=tick_id)
    authorities: list[dict[str, Any]] = [receipt.to_canonical_dict()]
    if receipt.reconciliation_id is not None:
        reconciliation = repository.get_reconciliation(receipt.reconciliation_id)
        authorities.append(reconciliation.to_canonical_dict())
    if receipt.summary_id is not None:
        summary = repository.get_summary(receipt.summary_id)
        authorities.append(summary.to_canonical_dict())
        if summary.lineage.continuous_operation_id != run_id:
            raise ValueError("Decision Replay operation lineage mismatch")
        if summary.lineage.runtime_tick_id != tick_id:
            raise ValueError("Decision Replay tick lineage mismatch")
    if receipt.proposal_id is not None:
        proposal = repository.get_proposal(receipt.proposal_id)
        authorities.append(proposal.to_canonical_dict())
        if receipt.summary_id is not None and proposal.summary_id != receipt.summary_id:
            preview = repository.get_summary(proposal.summary_id)
            authorities.append(preview.to_canonical_dict())
            if preview.account_id != proposal.account_id:
                raise ValueError("Decision Replay Proposal/Summary lineage mismatch")
    if receipt.risk_decision_id is not None:
        risk = repository.get_risk_decision(receipt.risk_decision_id)
        authorities.append(risk.to_canonical_dict())
        if receipt.proposal_id != risk.proposal_id:
            raise ValueError("Decision Replay Risk/Proposal lineage mismatch")
    stage_artifacts = {item.artifact_id: item.artifact_hash for item in receipt.stage_receipts if item.artifact_id is not None}
    for authority in authorities[1:]:
        identity, content_hash = _identity_and_hash(authority)
        if identity not in stage_artifacts and identity != receipt.summary_id:
            raise ValueError("Decision Replay stage authority is unbound")
        if identity in stage_artifacts and stage_artifacts[identity] != content_hash:
            raise ValueError("Decision Replay stage hash mismatch")
    replay_hash = canonical_hash(
        {
            "schema_version": "decision-system-replay-v1",
            "run_id": str(run_id),
            "tick_id": str(tick_id),
            "authorities": authorities,
        }
    )
    return DecisionSystemReplayResult(
        run_id=run_id,
        tick_id=tick_id,
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        replay_hash=replay_hash,
        verified_authority_count=len(authorities),
    )


def _identity_and_hash(payload: dict[str, Any]) -> tuple[ArtifactId, str]:
    for id_name, hash_name in (
        ("risk_decision_id", "content_hash"),
        ("proposal_id", "content_hash"),
        ("summary_id", "content_hash"),
        ("reconciliation_id", "content_hash"),
    ):
        if id_name in payload:
            return ArtifactId(str(payload[id_name])), str(payload[hash_name])
    raise ValueError("Decision Replay authority identity is unknown")


__all__ = ["DecisionSystemReplayResult", "replay_decision_system"]
