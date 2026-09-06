"""Continuation decisions over exact immutable Target and exchange sessions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from market_regime_alpha.market.application.archive_manifest import ArchiveOperatorManifest
from market_regime_alpha.market.domain import (
    ProspectiveArchiveSession, TargetArchiveSessions,
    derive_target_archive_sessions, target_aligned_capture_windows,
)
from market_regime_alpha.market.ports import TargetArchiveContract


@dataclass(frozen=True, slots=True)
class ProspectiveContinuationPlan:
    missed_decision_session_ids: tuple[UUID, ...]
    next_sessions: TargetArchiveSessions | None
    blocked_reason: str | None = None
    blocked_decision_session_id: UUID | None = None


def plan_continuation(
    manifest: ArchiveOperatorManifest, *, contract: TargetArchiveContract,
    sessions: tuple[ProspectiveArchiveSession, ...], observed_at: datetime,
) -> ProspectiveContinuationPlan:
    generation = manifest.start_request.prospective_generation
    if generation is None:
        raise ValueError("Continuity requires an exact prospective generation")
    if (contract.target_definition_id, contract.version, str(contract.content_sha256)) != (
        generation.target_definition_id, generation.target_version,
        str(generation.target_definition_sha256),
    ):
        raise ValueError("Continuation Target differs from the frozen generation")
    if observed_at.tzinfo is None:
        raise ValueError("Continuation clock requires a timezone")
    if (not sessions or any(item.exchange != generation.exchange for item in sessions)
            or len({item.session_id for item in sessions}) != len(sessions)
            or tuple(item.session_date for item in sessions) != tuple(sorted(item.session_date for item in sessions))):
        raise ValueError("Continuation requires an unambiguous exact exchange calendar")
    indexes = {item.session_id: index for index, item in enumerate(sessions)}
    if generation.decision_session_id not in indexes:
        raise ValueError("Head generation Session is absent from canonical calendar")
    head = indexes[generation.decision_session_id]
    if observed_at < sessions[head].close_at:
        return ProspectiveContinuationPlan((), None)
    next_id = sessions[head + 1].session_id if head + 1 < len(sessions) else None
    if generation.later_verification_session_id not in indexes:
        return ProspectiveContinuationPlan((), None, "CALENDAR_INCOMPLETE", next_id)
    later_offset = indexes[generation.later_verification_session_id] - head
    missed: list[UUID] = []
    for index in range(head + 1, len(sessions)):
        candidate = sessions[index]
        if index + later_offset >= len(sessions):
            return ProspectiveContinuationPlan(tuple(missed), None, "CALENDAR_INCOMPLETE", candidate.session_id)
        resolved = derive_target_archive_sessions(
            exchange=generation.exchange, decision_session_id=candidate.session_id,
            sessions=sessions, checkpoints=contract.checkpoints,
            later_verification_session_offset=later_offset,
        )
        if min(window.window_start for window in target_aligned_capture_windows(resolved)) < observed_at:
            missed.append(candidate.session_id)
            continue
        return ProspectiveContinuationPlan(tuple(missed), resolved)
    return ProspectiveContinuationPlan(tuple(missed), None, "CALENDAR_INCOMPLETE")
