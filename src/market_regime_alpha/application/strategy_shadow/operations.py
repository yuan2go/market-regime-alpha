"""Recoverable event journal and daily reporting for Strategy Shadow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class StrategyShadowSessionStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"


class StrategyShadowEventKind(str, Enum):
    SCHEDULED = "SCHEDULED"
    STARTED = "STARTED"
    ENTRY_CREATED = "ENTRY_CREATED"
    FILL_OBSERVED = "FILL_OBSERVED"
    POSITION_OPENED = "POSITION_OPENED"
    HOLDING_ASSESSED = "HOLDING_ASSESSED"
    EXIT_ASSESSED = "EXIT_ASSESSED"
    OUTCOME_SETTLED = "OUTCOME_SETTLED"
    INCIDENT_RECORDED = "INCIDENT_RECORDED"
    DRIFT_RECORDED = "DRIFT_RECORDED"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"


class StrategyShadowArtifactKind(str, Enum):
    POLICY = "POLICY"
    ENTRY = "ENTRY"
    FILL = "FILL"
    POSITION = "POSITION"
    HOLDING_ASSESSMENT = "HOLDING_ASSESSMENT"
    EXIT_ASSESSMENT = "EXIT_ASSESSMENT"
    STRATEGY_OUTCOME = "STRATEGY_OUTCOME"
    DAILY_REPORT = "DAILY_REPORT"


@dataclass(frozen=True, slots=True)
class StrategyShadowEvent:
    event_id: ArtifactId
    event_hash: str
    session_id: ArtifactId
    sequence: int
    event_kind: StrategyShadowEventKind
    occurred_at: datetime
    artifact_reference: ValidationArtifactReference | None
    details: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.sequence <= 0 or self.details != tuple(sorted(set(self.details))):
            raise ValueError("Strategy Shadow event sequence/details invalid")
        if canonical_hash(self.identity_payload()) != self.event_hash:
            raise ValueError("Strategy Shadow event hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "sequence": self.sequence,
            "event_kind": self.event_kind.value,
            "occurred_at": timestamp(self.occurred_at),
            "artifact_reference": None if self.artifact_reference is None else self.artifact_reference.to_canonical_dict(),
            "details": [list(item) for item in self.details],
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"event_id": str(self.event_id), "event_hash": self.event_hash, **self.identity_payload()}

    @classmethod
    def create(
        cls,
        *,
        session_id: ArtifactId,
        sequence: int,
        event_kind: StrategyShadowEventKind,
        occurred_at: datetime,
        artifact_reference: ValidationArtifactReference | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> StrategyShadowEvent:
        if sequence <= 0 or details != tuple(sorted(set(details))):
            raise ValueError("Strategy Shadow event sequence/details invalid")
        payload = {
            "session_id": str(session_id),
            "sequence": sequence,
            "event_kind": event_kind.value,
            "occurred_at": timestamp(occurred_at),
            "artifact_reference": None if artifact_reference is None else artifact_reference.to_canonical_dict(),
            "details": [list(item) for item in details],
        }
        artifact_id, digest = content_identity("strategy-shadow-event", payload)
        return cls(artifact_id, digest, session_id, sequence, event_kind, occurred_at, artifact_reference, details)


@dataclass(frozen=True, slots=True)
class StrategyShadowSession:
    session_id: ArtifactId
    session_hash: str
    trading_date: date
    scheduled_for: datetime
    research_shadow_reference: ValidationArtifactReference
    runtime_run_reference: ValidationArtifactReference
    runtime_tick_reference: ValidationArtifactReference
    policy_reference: ValidationArtifactReference
    status: StrategyShadowSessionStatus
    revision: int
    events: tuple[StrategyShadowEvent, ...]
    created_at: datetime
    updated_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "strategy-shadow-session/v1"

    def __post_init__(self) -> None:
        require_sha256("session_hash", self.session_hash)
        sequences = tuple(item.sequence for item in self.events)
        if sequences != tuple(range(1, len(self.events) + 1)) or any(item.session_id != self.session_id for item in self.events):
            raise ValueError("Strategy Shadow journal is not contiguous")
        if canonical_hash(self.identity_payload()) != self.session_hash:
            raise ValueError("Strategy Shadow session hash mismatch")

    @classmethod
    def schedule(
        cls,
        *,
        trading_date: date,
        scheduled_for: datetime,
        research_shadow_reference: ValidationArtifactReference,
        runtime_run_reference: ValidationArtifactReference,
        runtime_tick_reference: ValidationArtifactReference,
        policy_reference: ValidationArtifactReference,
        created_at: datetime,
    ) -> StrategyShadowSession:
        seed = {
            "trading_date": trading_date.isoformat(),
            "scheduled_for": timestamp(scheduled_for),
            "research_shadow_reference": research_shadow_reference.to_canonical_dict(),
            "runtime_run_reference": runtime_run_reference.to_canonical_dict(),
            "runtime_tick_reference": runtime_tick_reference.to_canonical_dict(),
            "policy_reference": policy_reference.to_canonical_dict(),
        }
        session_id, _seed_hash = content_identity("strategy-shadow-session", seed)
        event = StrategyShadowEvent.create(
            session_id=session_id, sequence=1, event_kind=StrategyShadowEventKind.SCHEDULED, occurred_at=created_at
        )
        limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "STRATEGY_SHADOW_PROVEN_FALSE", "NOT_SUSTAINED_PROSPECTIVE_EVIDENCE"}))
        values = (
            session_id,
            "",
            trading_date,
            scheduled_for,
            research_shadow_reference,
            runtime_run_reference,
            runtime_tick_reference,
            policy_reference,
            StrategyShadowSessionStatus.SCHEDULED,
            1,
            (event,),
            created_at,
            created_at,
            limitations,
        )
        payload = _session_payload(*values[2:])
        digest = canonical_hash(payload)
        return cls(session_id, digest, *values[2:])

    def append(
        self,
        *,
        event_kind: StrategyShadowEventKind,
        occurred_at: datetime,
        artifact_reference: ValidationArtifactReference | None = None,
        details: tuple[tuple[str, str], ...] = (),
        status: StrategyShadowSessionStatus | None = None,
    ) -> StrategyShadowSession:
        next_status = self.status if status is None else status
        _validate_transition(self.status, event_kind, next_status)
        _validate_event_prerequisites(self.events, event_kind)
        event = StrategyShadowEvent.create(
            session_id=self.session_id,
            sequence=len(self.events) + 1,
            event_kind=event_kind,
            occurred_at=occurred_at,
            artifact_reference=artifact_reference,
            details=tuple(sorted(set(details))),
        )
        values = (
            self.trading_date,
            self.scheduled_for,
            self.research_shadow_reference,
            self.runtime_run_reference,
            self.runtime_tick_reference,
            self.policy_reference,
            next_status,
            self.revision + 1,
            (*self.events, event),
            self.created_at,
            occurred_at,
            self.limitations,
        )
        digest = canonical_hash(_session_payload(*values))
        return StrategyShadowSession(self.session_id, digest, *values)

    def identity_payload(self) -> dict[str, Any]:
        return _session_payload(
            self.trading_date,
            self.scheduled_for,
            self.research_shadow_reference,
            self.runtime_run_reference,
            self.runtime_tick_reference,
            self.policy_reference,
            self.status,
            self.revision,
            self.events,
            self.created_at,
            self.updated_at,
            self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "session_hash": self.session_hash,
            **self.identity_payload(),
        }


class StrategyShadowRepository(Protocol):
    def get(self, session_id: ArtifactId) -> StrategyShadowSession | None: ...
    def save(self, session: StrategyShadowSession, *, expected_revision: int | None) -> None: ...

    def save_with_artifact(
        self,
        session: StrategyShadowSession,
        *,
        expected_revision: int,
        artifact: StrategyShadowArtifactRecord,
    ) -> None: ...

    def save_artifact(self, artifact: StrategyShadowArtifactRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class StrategyShadowArtifactRecord:
    artifact_reference: ValidationArtifactReference
    artifact_kind: StrategyShadowArtifactKind
    session_id: ArtifactId | None
    payload: dict[str, Any]
    created_at: datetime

    def __post_init__(self) -> None:
        if canonical_hash(self.payload) != self.artifact_reference.content_hash:
            raise ValueError("Strategy Shadow Artifact payload hash mismatch")
        if (self.artifact_kind is StrategyShadowArtifactKind.DAILY_REPORT) != (self.session_id is None):
            raise ValueError("only daily reports are independent of one Strategy Shadow session")
        expected_reference_kind = {
            StrategyShadowArtifactKind.POLICY: "STRATEGY_SHADOW_POLICY",
            StrategyShadowArtifactKind.ENTRY: "SHADOW_ENTRY",
            StrategyShadowArtifactKind.FILL: "SHADOW_FILL",
            StrategyShadowArtifactKind.POSITION: "SHADOW_POSITION",
            StrategyShadowArtifactKind.HOLDING_ASSESSMENT: "HOLDING_ASSESSMENT",
            StrategyShadowArtifactKind.EXIT_ASSESSMENT: "EXIT_ASSESSMENT",
            StrategyShadowArtifactKind.STRATEGY_OUTCOME: "STRATEGY_OUTCOME",
            StrategyShadowArtifactKind.DAILY_REPORT: "STRATEGY_SHADOW_DAILY_REPORT",
        }[self.artifact_kind]
        if self.artifact_reference.artifact_kind != expected_reference_kind:
            raise ValueError(f"{self.artifact_kind.value} requires {expected_reference_kind}")


class InMemoryStrategyShadowRepository:
    def __init__(self) -> None:
        self._sessions: dict[ArtifactId, StrategyShadowSession] = {}
        self._artifacts: dict[ArtifactId, StrategyShadowArtifactRecord] = {}

    def get(self, session_id: ArtifactId) -> StrategyShadowSession | None:
        return self._sessions.get(session_id)

    def save(self, session: StrategyShadowSession, *, expected_revision: int | None) -> None:
        existing = self._sessions.get(session.session_id)
        actual = None if existing is None else existing.revision
        if actual != expected_revision:
            raise ValueError("Strategy Shadow CAS conflict")
        self._sessions[session.session_id] = session

    def save_with_artifact(
        self,
        session: StrategyShadowSession,
        *,
        expected_revision: int,
        artifact: StrategyShadowArtifactRecord,
    ) -> None:
        if artifact.session_id != session.session_id:
            raise ValueError("Strategy Shadow Artifact/session mismatch")
        self.save(session, expected_revision=expected_revision)
        self.save_artifact(artifact)

    def save_artifact(self, artifact: StrategyShadowArtifactRecord) -> None:
        existing = self._artifacts.get(artifact.artifact_reference.artifact_id)
        if existing is not None and existing != artifact:
            raise ValueError("Strategy Shadow Artifact identity conflict")
        self._artifacts[artifact.artifact_reference.artifact_id] = artifact


def replay_strategy_shadow(session: StrategyShadowSession) -> StrategyShadowSession:
    if not session.events or session.events[0].event_kind is not StrategyShadowEventKind.SCHEDULED:
        raise ValueError("Strategy Shadow replay requires Scheduled root")
    if session.events[-1].sequence != session.revision:
        raise ValueError("Strategy Shadow revision/event divergence")
    status = StrategyShadowSessionStatus.SCHEDULED
    for event in session.events[1:]:
        next_status = _status_after_event(status, event.event_kind)
        _validate_transition(status, event.event_kind, next_status)
        status = next_status
    if status is not session.status:
        raise ValueError("Strategy Shadow event replay status divergence")
    if canonical_hash(session.identity_payload()) != session.session_hash:
        raise ValueError("Strategy Shadow replay hash mismatch")
    return session


def strategy_shadow_session_from_canonical_dict(value: dict[str, Any]) -> StrategyShadowSession:
    events = tuple(
        StrategyShadowEvent(
            event_id=ArtifactId(str(item["event_id"])),
            event_hash=str(item["event_hash"]),
            session_id=ArtifactId(str(value["session_id"])),
            sequence=int(item["sequence"]),
            event_kind=StrategyShadowEventKind(str(item["event_kind"])),
            occurred_at=datetime.fromisoformat(str(item["occurred_at"])),
            artifact_reference=(None if item["artifact_reference"] is None else _reference_from_dict(item["artifact_reference"])),
            details=tuple((str(pair[0]), str(pair[1])) for pair in item["details"]),
        )
        for item in value["events"]
    )
    return StrategyShadowSession(
        session_id=ArtifactId(str(value["session_id"])),
        session_hash=str(value["session_hash"]),
        trading_date=date.fromisoformat(str(value["trading_date"])),
        scheduled_for=datetime.fromisoformat(str(value["scheduled_for"])),
        research_shadow_reference=_reference_from_dict(value["research_shadow_reference"]),
        runtime_run_reference=_reference_from_dict(value["runtime_run_reference"]),
        runtime_tick_reference=_reference_from_dict(value["runtime_tick_reference"]),
        policy_reference=_reference_from_dict(value["policy_reference"]),
        status=StrategyShadowSessionStatus(str(value["status"])),
        revision=int(value["revision"]),
        events=events,
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
        limitations=tuple(str(item) for item in value["limitations"]),
        schema_version=str(value["schema_version"]),
    )


@dataclass(frozen=True, slots=True)
class StrategyShadowDailyReport:
    report_id: ArtifactId
    report_hash: str
    trading_date: date
    session_references: tuple[ValidationArtifactReference, ...]
    scheduled_count: int
    settled_count: int
    failed_count: int
    incident_count: int
    drift_count: int
    generated_at: datetime
    sustained_prospective_proof: bool
    limitations: tuple[str, ...]


def build_daily_report(
    *, trading_date: date, sessions: tuple[StrategyShadowSession, ...], generated_at: datetime
) -> StrategyShadowDailyReport:
    scoped = tuple(sorted((item for item in sessions if item.trading_date == trading_date), key=lambda item: str(item.session_id)))
    references = tuple(ValidationArtifactReference("STRATEGY_SHADOW_SESSION", item.session_id, item.session_hash) for item in scoped)
    incident_count = sum(event.event_kind is StrategyShadowEventKind.INCIDENT_RECORDED for item in scoped for event in item.events)
    drift_count = sum(event.event_kind is StrategyShadowEventKind.DRIFT_RECORDED for item in scoped for event in item.events)
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "STRATEGY_SHADOW_PROVEN_FALSE", "NOT_SUSTAINED_PROSPECTIVE_EVIDENCE"}))
    payload = {
        "trading_date": trading_date.isoformat(),
        "session_references": [item.to_canonical_dict() for item in references],
        "scheduled_count": len(scoped),
        "settled_count": sum(item.status is StrategyShadowSessionStatus.SETTLED for item in scoped),
        "failed_count": sum(item.status is StrategyShadowSessionStatus.FAILED for item in scoped),
        "incident_count": incident_count,
        "drift_count": drift_count,
        "generated_at": timestamp(generated_at),
        "sustained_prospective_proof": False,
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("strategy-shadow-daily-report", payload)
    return StrategyShadowDailyReport(
        artifact_id,
        digest,
        trading_date,
        references,
        len(scoped),
        sum(item.status is StrategyShadowSessionStatus.SETTLED for item in scoped),
        sum(item.status is StrategyShadowSessionStatus.FAILED for item in scoped),
        incident_count,
        drift_count,
        generated_at,
        False,
        limitations,
    )


class StrategyShadowOperations:
    """Controlled lifecycle over an existing Runtime/Research Shadow lineage."""

    def __init__(self, repository: StrategyShadowRepository) -> None:
        self._repository = repository

    def schedule(self, **values: Any) -> StrategyShadowSession:
        session = StrategyShadowSession.schedule(**values)
        self._repository.save(session, expected_revision=None)
        return self._repository.get(session.session_id) or session

    def start(self, session_id: ArtifactId, *, expected_revision: int, occurred_at: datetime) -> StrategyShadowSession:
        return self._append(
            session_id,
            expected_revision=expected_revision,
            event_kind=StrategyShadowEventKind.STARTED,
            occurred_at=occurred_at,
            status=StrategyShadowSessionStatus.RUNNING,
        )

    def record_artifact(
        self,
        session_id: ArtifactId,
        *,
        expected_revision: int,
        event_kind: StrategyShadowEventKind,
        artifact: StrategyShadowArtifactRecord,
        occurred_at: datetime,
    ) -> StrategyShadowSession:
        if event_kind not in {
            StrategyShadowEventKind.ENTRY_CREATED,
            StrategyShadowEventKind.FILL_OBSERVED,
            StrategyShadowEventKind.POSITION_OPENED,
            StrategyShadowEventKind.HOLDING_ASSESSED,
            StrategyShadowEventKind.EXIT_ASSESSED,
            StrategyShadowEventKind.OUTCOME_SETTLED,
        }:
            raise ValueError("Strategy Shadow Artifact event kind is invalid")
        expected_artifact_kind = {
            StrategyShadowEventKind.ENTRY_CREATED: StrategyShadowArtifactKind.ENTRY,
            StrategyShadowEventKind.FILL_OBSERVED: StrategyShadowArtifactKind.FILL,
            StrategyShadowEventKind.POSITION_OPENED: StrategyShadowArtifactKind.POSITION,
            StrategyShadowEventKind.HOLDING_ASSESSED: StrategyShadowArtifactKind.HOLDING_ASSESSMENT,
            StrategyShadowEventKind.EXIT_ASSESSED: StrategyShadowArtifactKind.EXIT_ASSESSMENT,
            StrategyShadowEventKind.OUTCOME_SETTLED: StrategyShadowArtifactKind.STRATEGY_OUTCOME,
        }[event_kind]
        if artifact.artifact_kind is not expected_artifact_kind:
            raise ValueError(f"{event_kind.value} requires {expected_artifact_kind.value} Artifact")
        current = self._require_revision(session_id, expected_revision)
        next_status = (
            StrategyShadowSessionStatus.SETTLED
            if event_kind is StrategyShadowEventKind.OUTCOME_SETTLED
            else StrategyShadowSessionStatus.RUNNING
        )
        updated = current.append(
            event_kind=event_kind,
            occurred_at=occurred_at,
            artifact_reference=artifact.artifact_reference,
            status=next_status,
        )
        self._repository.save_with_artifact(updated, expected_revision=expected_revision, artifact=artifact)
        return self._repository.get(session_id) or updated

    def incident(self, session_id: ArtifactId, *, expected_revision: int, occurred_at: datetime, code: str) -> StrategyShadowSession:
        return self._append(
            session_id,
            expected_revision=expected_revision,
            event_kind=StrategyShadowEventKind.INCIDENT_RECORDED,
            occurred_at=occurred_at,
            details=(("code", code),),
        )

    def drift(self, session_id: ArtifactId, *, expected_revision: int, occurred_at: datetime, code: str) -> StrategyShadowSession:
        return self._append(
            session_id,
            expected_revision=expected_revision,
            event_kind=StrategyShadowEventKind.DRIFT_RECORDED,
            occurred_at=occurred_at,
            details=(("code", code),),
        )

    def fail(self, session_id: ArtifactId, *, expected_revision: int, occurred_at: datetime, code: str) -> StrategyShadowSession:
        return self._append(
            session_id,
            expected_revision=expected_revision,
            event_kind=StrategyShadowEventKind.FAILED,
            occurred_at=occurred_at,
            details=(("code", code),),
            status=StrategyShadowSessionStatus.FAILED,
        )

    def recover(self, session_id: ArtifactId, *, expected_revision: int, occurred_at: datetime, reason: str) -> StrategyShadowSession:
        return self._append(
            session_id,
            expected_revision=expected_revision,
            event_kind=StrategyShadowEventKind.RECOVERED,
            occurred_at=occurred_at,
            details=(("reason", reason),),
            status=StrategyShadowSessionStatus.RUNNING,
        )

    def replay(self, session_id: ArtifactId) -> StrategyShadowSession:
        session = self._repository.get(session_id)
        if session is None:
            raise KeyError(str(session_id))
        return replay_strategy_shadow(session)

    def daily_report(
        self, *, trading_date: date, sessions: tuple[StrategyShadowSession, ...], generated_at: datetime
    ) -> StrategyShadowDailyReport:
        report = build_daily_report(trading_date=trading_date, sessions=sessions, generated_at=generated_at)
        self._repository.save_artifact(
            StrategyShadowArtifactRecord(
                ValidationArtifactReference("STRATEGY_SHADOW_DAILY_REPORT", report.report_id, report.report_hash),
                StrategyShadowArtifactKind.DAILY_REPORT,
                None,
                _daily_report_payload(report),
                generated_at,
            )
        )
        return report

    def _append(
        self,
        session_id: ArtifactId,
        *,
        expected_revision: int,
        event_kind: StrategyShadowEventKind,
        occurred_at: datetime,
        details: tuple[tuple[str, str], ...] = (),
        status: StrategyShadowSessionStatus | None = None,
    ) -> StrategyShadowSession:
        current = self._require_revision(session_id, expected_revision)
        updated = current.append(event_kind=event_kind, occurred_at=occurred_at, details=details, status=status)
        self._repository.save(updated, expected_revision=expected_revision)
        return self._repository.get(session_id) or updated

    def _require_revision(self, session_id: ArtifactId, expected_revision: int) -> StrategyShadowSession:
        current = self._repository.get(session_id)
        if current is None:
            raise KeyError(str(session_id))
        if current.revision != expected_revision:
            raise ValueError("Strategy Shadow CAS conflict")
        return current


def _session_payload(
    trading_date: date,
    scheduled_for: datetime,
    research: ValidationArtifactReference,
    run: ValidationArtifactReference,
    tick: ValidationArtifactReference,
    policy: ValidationArtifactReference,
    status: StrategyShadowSessionStatus,
    revision: int,
    events: tuple[StrategyShadowEvent, ...],
    created_at: datetime,
    updated_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "strategy-shadow-session/v1",
        "trading_date": trading_date.isoformat(),
        "scheduled_for": timestamp(scheduled_for),
        "research_shadow_reference": research.to_canonical_dict(),
        "runtime_run_reference": run.to_canonical_dict(),
        "runtime_tick_reference": tick.to_canonical_dict(),
        "policy_reference": policy.to_canonical_dict(),
        "status": status.value,
        "revision": revision,
        "events": [
            {
                "event_id": str(item.event_id),
                "event_hash": item.event_hash,
                "sequence": item.sequence,
                "event_kind": item.event_kind.value,
                "occurred_at": timestamp(item.occurred_at),
                "artifact_reference": None if item.artifact_reference is None else item.artifact_reference.to_canonical_dict(),
                "details": [list(value) for value in item.details],
            }
            for item in events
        ],
        "created_at": timestamp(created_at),
        "updated_at": timestamp(updated_at),
        "limitations": list(limitations),
    }


def _status_after_event(current: StrategyShadowSessionStatus, event_kind: StrategyShadowEventKind) -> StrategyShadowSessionStatus:
    if event_kind in {StrategyShadowEventKind.STARTED, StrategyShadowEventKind.RECOVERED}:
        return StrategyShadowSessionStatus.RUNNING
    if event_kind is StrategyShadowEventKind.OUTCOME_SETTLED:
        return StrategyShadowSessionStatus.SETTLED
    if event_kind is StrategyShadowEventKind.FAILED:
        return StrategyShadowSessionStatus.FAILED
    return current


def _validate_transition(
    current: StrategyShadowSessionStatus,
    event_kind: StrategyShadowEventKind,
    next_status: StrategyShadowSessionStatus,
) -> None:
    if current is StrategyShadowSessionStatus.SETTLED:
        raise ValueError("settled Strategy Shadow session is terminal")
    allowed = {
        StrategyShadowSessionStatus.SCHEDULED: {
            StrategyShadowEventKind.STARTED,
            StrategyShadowEventKind.FAILED,
        },
        StrategyShadowSessionStatus.RUNNING: {
            StrategyShadowEventKind.ENTRY_CREATED,
            StrategyShadowEventKind.FILL_OBSERVED,
            StrategyShadowEventKind.POSITION_OPENED,
            StrategyShadowEventKind.HOLDING_ASSESSED,
            StrategyShadowEventKind.EXIT_ASSESSED,
            StrategyShadowEventKind.OUTCOME_SETTLED,
            StrategyShadowEventKind.INCIDENT_RECORDED,
            StrategyShadowEventKind.DRIFT_RECORDED,
            StrategyShadowEventKind.RECOVERED,
            StrategyShadowEventKind.FAILED,
        },
        StrategyShadowSessionStatus.FAILED: {
            StrategyShadowEventKind.RECOVERED,
            StrategyShadowEventKind.INCIDENT_RECORDED,
            StrategyShadowEventKind.DRIFT_RECORDED,
        },
    }.get(current, set())
    if event_kind not in allowed or next_status is not _status_after_event(current, event_kind):
        raise ValueError(f"invalid Strategy Shadow transition {current.value}/{event_kind.value}/{next_status.value}")


def _validate_event_prerequisites(
    events: tuple[StrategyShadowEvent, ...],
    event_kind: StrategyShadowEventKind,
) -> None:
    kinds = tuple(item.event_kind for item in events)
    requirements = {
        StrategyShadowEventKind.ENTRY_CREATED: (StrategyShadowEventKind.STARTED,),
        StrategyShadowEventKind.FILL_OBSERVED: (StrategyShadowEventKind.ENTRY_CREATED,),
        StrategyShadowEventKind.POSITION_OPENED: (StrategyShadowEventKind.FILL_OBSERVED,),
        StrategyShadowEventKind.HOLDING_ASSESSED: (StrategyShadowEventKind.POSITION_OPENED,),
        StrategyShadowEventKind.EXIT_ASSESSED: (StrategyShadowEventKind.HOLDING_ASSESSED,),
        StrategyShadowEventKind.OUTCOME_SETTLED: (StrategyShadowEventKind.EXIT_ASSESSED,),
    }
    required = requirements.get(event_kind, ())
    if any(item not in kinds for item in required):
        missing = ",".join(item.value for item in required if item not in kinds)
        raise ValueError(f"Strategy Shadow {event_kind.value} missing prerequisite {missing}")
    singletons = {
        StrategyShadowEventKind.STARTED,
        StrategyShadowEventKind.ENTRY_CREATED,
        StrategyShadowEventKind.FILL_OBSERVED,
        StrategyShadowEventKind.POSITION_OPENED,
        StrategyShadowEventKind.EXIT_ASSESSED,
        StrategyShadowEventKind.OUTCOME_SETTLED,
    }
    if event_kind in singletons and event_kind in kinds:
        raise ValueError(f"Strategy Shadow {event_kind.value} already recorded")


def _daily_report_payload(report: StrategyShadowDailyReport) -> dict[str, Any]:
    return {
        "trading_date": report.trading_date.isoformat(),
        "session_references": [item.to_canonical_dict() for item in report.session_references],
        "scheduled_count": report.scheduled_count,
        "settled_count": report.settled_count,
        "failed_count": report.failed_count,
        "incident_count": report.incident_count,
        "drift_count": report.drift_count,
        "generated_at": timestamp(report.generated_at),
        "sustained_prospective_proof": report.sustained_prospective_proof,
        "limitations": list(report.limitations),
    }


def _reference_from_dict(value: Any) -> ValidationArtifactReference:
    if not isinstance(value, dict):
        raise ValueError("Strategy Shadow reference must be an object")
    return ValidationArtifactReference.from_canonical_dict(value)
