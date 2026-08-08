"""Credential-free structured report over the Continuous Research Journal."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId


def build_continuous_research_report(
    journal: PostgresContinuousResearchJournal, run_id: ArtifactId
) -> dict[str, Any]:
    snapshot = journal.get_run(run_id)
    return {
        "schema_version": "continuous-research-report-v1",
        "status": snapshot.status.value,
        "run_id": str(snapshot.command.run_id),
        "trading_date": snapshot.command.trading_date.isoformat(),
        "request_scope_hash": snapshot.command.request_scope_hash,
        "current_tick_sequence": snapshot.current_tick_sequence,
        "tick_count": len(snapshot.ticks),
        "ticks": [
            {
                "tick_id": str(item.command.tick_id),
                "tick_sequence": item.tick_sequence,
                "observed_at": item.command.observed_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "session_phase": item.session_phase.value,
                "status": item.status.value,
                "fencing_token": item.fencing_token,
                "provider_attempt_id": item.provider_attempt_id,
                "evidence_commit_id": (
                    None
                    if item.evidence_commit_id is None
                    else str(item.evidence_commit_id)
                ),
                "change_decision_id": (
                    None
                    if item.change_decision_id is None
                    else str(item.change_decision_id)
                ),
                "receipt_id": (
                    None if item.receipt is None else str(item.receipt.receipt_id)
                ),
                "last_error": item.last_error,
            }
            for item in snapshot.ticks
        ],
        "event_count": len(snapshot.events),
        "limitations": list(snapshot.command.limitations),
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


__all__ = ["build_continuous_research_report"]
