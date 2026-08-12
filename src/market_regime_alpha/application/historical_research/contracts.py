"""Immutable command for one historical range over a frozen trading calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
    ResearchDecisionSessionRequest,
    ResearchExecutionMode,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)


HISTORICAL_RESEARCH_COMMAND_SCHEMA = "historical-research-command/v1"


@dataclass(frozen=True, slots=True)
class HistoricalResearchCommand:
    run_id: ArtifactId
    command_hash: str
    idempotency_key: str
    start_date: date
    end_date: date
    trading_sessions: tuple[date, ...]
    decision_local_time: time
    timezone_name: str
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    runtime_scope_policy_id: ArtifactId
    runtime_scope_policy_hash: str
    decision_policy_id: ArtifactId
    decision_policy_hash: str
    target_protocol_reference: ValidationArtifactReference
    experiment_definition_reference: ValidationArtifactReference
    configuration_references: tuple[ValidationArtifactReference, ...]
    data_authority_mode: DataAuthorityMode
    evidence_qualification: EvidenceQualification
    code_revision: str
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = HISTORICAL_RESEARCH_COMMAND_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_RESEARCH_COMMAND_SCHEMA:
            raise ValueError("unsupported Historical Research command schema")
        require_sha256("command_hash", self.command_hash)
        for label, value in (
            ("trading_calendar_hash", self.trading_calendar_hash),
            ("runtime_scope_policy_hash", self.runtime_scope_policy_hash),
            ("decision_policy_hash", self.decision_policy_hash),
        ):
            require_sha256(label, value)
        require_text("idempotency_key", self.idempotency_key)
        require_text("timezone_name", self.timezone_name)
        require_text("code_revision", self.code_revision)
        if self.target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Historical Research requires canonical Target Protocol")
        if (
            self.experiment_definition_reference.artifact_kind
            != "RESEARCH_EXPERIMENT_DEFINITION"
        ):
            raise ValueError("Historical Research requires frozen Experiment Definition")
        ZoneInfo(self.timezone_name)
        if self.start_date > self.end_date:
            raise ValueError("Historical Research start_date exceeds end_date")
        if not self.trading_sessions or self.trading_sessions != tuple(
            sorted(set(self.trading_sessions))
        ):
            raise ValueError("trading_sessions must be non-empty, sorted and unique")
        if self.trading_sessions[0] < self.start_date or (
            self.trading_sessions[-1] > self.end_date
        ):
            raise ValueError("trading session is outside the requested period")
        if self.decision_local_time.tzinfo is not None:
            raise ValueError("decision_local_time must be a wall-clock time")
        normalize_canonical_datetime(self.created_at)
        if self.configuration_references != _references(
            self.configuration_references
        ):
            raise ValueError("configuration references must be unique and sorted")
        if not self.configuration_references:
            raise ValueError("Historical Research requires explicit configuration")
        if (
            self.data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE
            and self.evidence_qualification
            is EvidenceQualification.FORMAL_PIT_QUALIFIED
        ):
            raise ValueError("free Research data cannot claim Formal PIT")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Historical Research limitations must be unique and sorted")
        if self.data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE:
            required = {
                "FORMAL_OOS_FALSE",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "FREE_DATA_EXPLORATORY",
                "NO_TRADING_AUTHORITY",
                "PIT_INCOMPLETE",
            }
            if not required.issubset(self.limitations):
                raise ValueError("free Historical Research evidence ceiling is incomplete")
        digest = canonical_hash(self.semantic_payload())
        if digest != self.command_hash:
            raise ValueError("Historical Research command hash mismatch")
        if str(self.run_id) != f"historical-research-run-{digest[7:31]}":
            raise ValueError("Historical Research run identity mismatch")

    @property
    def session_count(self) -> int:
        return len(self.trading_sessions)

    @classmethod
    def create(
        cls,
        *,
        idempotency_key: str,
        start_date: date,
        end_date: date,
        trading_sessions: tuple[date, ...],
        decision_local_time: time,
        timezone_name: str,
        trading_calendar_id: ArtifactId,
        trading_calendar_hash: str,
        runtime_scope_policy_id: ArtifactId,
        runtime_scope_policy_hash: str,
        decision_policy_id: ArtifactId,
        decision_policy_hash: str,
        target_protocol_reference: ValidationArtifactReference,
        experiment_definition_reference: ValidationArtifactReference,
        configuration_references: tuple[ValidationArtifactReference, ...],
        data_authority_mode: DataAuthorityMode,
        evidence_qualification: EvidenceQualification,
        code_revision: str,
        created_at: datetime,
    ) -> HistoricalResearchCommand:
        ordered_sessions = tuple(trading_sessions)
        ordered_references = _references(configuration_references)
        limitations = (
            (
                "FORMAL_OOS_FALSE",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "FREE_DATA_EXPLORATORY",
                "NO_TRADING_AUTHORITY",
                "PIT_INCOMPLETE",
            )
            if data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE
            else ("NO_TRADING_AUTHORITY",)
        )
        values: dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "start_date": start_date,
            "end_date": end_date,
            "trading_sessions": ordered_sessions,
            "decision_local_time": decision_local_time,
            "timezone_name": timezone_name,
            "trading_calendar_id": trading_calendar_id,
            "trading_calendar_hash": trading_calendar_hash,
            "runtime_scope_policy_id": runtime_scope_policy_id,
            "runtime_scope_policy_hash": runtime_scope_policy_hash,
            "decision_policy_id": decision_policy_id,
            "decision_policy_hash": decision_policy_hash,
            "target_protocol_reference": target_protocol_reference,
            "experiment_definition_reference": experiment_definition_reference,
            "configuration_references": ordered_references,
            "data_authority_mode": data_authority_mode,
            "evidence_qualification": evidence_qualification,
            "code_revision": code_revision,
            "created_at": normalize_canonical_datetime(created_at),
            "limitations": limitations,
        }
        digest = canonical_hash(_command_payload(**values))
        return cls(
            run_id=ArtifactId(f"historical-research-run-{digest[7:31]}"),
            command_hash=digest,
            **values,
        )

    def session_request(self, trading_date: date) -> ResearchDecisionSessionRequest:
        if trading_date not in self.trading_sessions:
            raise KeyError(trading_date.isoformat())
        decision_time = datetime.combine(
            trading_date,
            self.decision_local_time,
            ZoneInfo(self.timezone_name),
        )
        return ResearchDecisionSessionRequest.create(
            trading_date=trading_date,
            decision_time=decision_time,
            materialized_at=self.created_at,
            data_authority_mode=self.data_authority_mode,
            execution_mode=ResearchExecutionMode.HISTORICAL_RESEARCH,
            evidence_qualification=self.evidence_qualification,
            trading_calendar_id=self.trading_calendar_id,
            trading_calendar_hash=self.trading_calendar_hash,
            runtime_scope_policy_id=self.runtime_scope_policy_id,
            runtime_scope_policy_hash=self.runtime_scope_policy_hash,
            decision_policy_id=self.decision_policy_id,
            decision_policy_hash=self.decision_policy_hash,
            target_protocol_reference=self.target_protocol_reference,
            experiment_definition_reference=self.experiment_definition_reference,
            code_revision=self.code_revision,
        )

    def semantic_values(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "trading_sessions": self.trading_sessions,
            "decision_local_time": self.decision_local_time,
            "timezone_name": self.timezone_name,
            "trading_calendar_id": self.trading_calendar_id,
            "trading_calendar_hash": self.trading_calendar_hash,
            "runtime_scope_policy_id": self.runtime_scope_policy_id,
            "runtime_scope_policy_hash": self.runtime_scope_policy_hash,
            "decision_policy_id": self.decision_policy_id,
            "decision_policy_hash": self.decision_policy_hash,
            "target_protocol_reference": self.target_protocol_reference,
            "experiment_definition_reference": self.experiment_definition_reference,
            "configuration_references": self.configuration_references,
            "data_authority_mode": self.data_authority_mode,
            "evidence_qualification": self.evidence_qualification,
            "code_revision": self.code_revision,
            "created_at": self.created_at,
        }

    def semantic_payload(self) -> dict[str, Any]:
        return _command_payload(
            **self.semantic_values(), limitations=self.limitations
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "command_hash": self.command_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalResearchCommand:
        return cls(
            run_id=ArtifactId(str(payload["run_id"])),
            command_hash=str(payload["command_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            start_date=date.fromisoformat(str(payload["start_date"])),
            end_date=date.fromisoformat(str(payload["end_date"])),
            trading_sessions=tuple(
                date.fromisoformat(str(item)) for item in payload["trading_sessions"]
            ),
            decision_local_time=time.fromisoformat(
                str(payload["decision_local_time"])
            ),
            timezone_name=str(payload["timezone_name"]),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            runtime_scope_policy_id=ArtifactId(
                str(payload["runtime_scope_policy_id"])
            ),
            runtime_scope_policy_hash=str(payload["runtime_scope_policy_hash"]),
            decision_policy_id=ArtifactId(str(payload["decision_policy_id"])),
            decision_policy_hash=str(payload["decision_policy_hash"]),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                payload["target_protocol_reference"]
            ),
            experiment_definition_reference=ValidationArtifactReference.from_canonical_dict(
                payload["experiment_definition_reference"]
            ),
            configuration_references=_references(
                tuple(
                    ValidationArtifactReference.from_canonical_dict(item)
                    for item in payload["configuration_references"]
                )
            ),
            data_authority_mode=DataAuthorityMode(
                str(payload["data_authority_mode"])
            ),
            evidence_qualification=EvidenceQualification(
                str(payload["evidence_qualification"])
            ),
            code_revision=str(payload["code_revision"]),
            created_at=datetime.fromisoformat(
                str(payload["created_at"]).replace("Z", "+00:00")
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def _command_payload(
    *,
    idempotency_key: str,
    start_date: date,
    end_date: date,
    trading_sessions: tuple[date, ...],
    decision_local_time: time,
    timezone_name: str,
    trading_calendar_id: ArtifactId,
    trading_calendar_hash: str,
    runtime_scope_policy_id: ArtifactId,
    runtime_scope_policy_hash: str,
    decision_policy_id: ArtifactId,
    decision_policy_hash: str,
    target_protocol_reference: ValidationArtifactReference,
    experiment_definition_reference: ValidationArtifactReference,
    configuration_references: tuple[ValidationArtifactReference, ...],
    data_authority_mode: DataAuthorityMode,
    evidence_qualification: EvidenceQualification,
    code_revision: str,
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_RESEARCH_COMMAND_SCHEMA,
        "idempotency_key": idempotency_key,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "trading_sessions": [item.isoformat() for item in trading_sessions],
        "decision_local_time": decision_local_time.isoformat(),
        "timezone_name": timezone_name,
        "trading_calendar_id": str(trading_calendar_id),
        "trading_calendar_hash": trading_calendar_hash,
        "runtime_scope_policy_id": str(runtime_scope_policy_id),
        "runtime_scope_policy_hash": runtime_scope_policy_hash,
        "decision_policy_id": str(decision_policy_id),
        "decision_policy_hash": decision_policy_hash,
        "target_protocol_reference": target_protocol_reference.to_canonical_dict(),
        "experiment_definition_reference": (
            experiment_definition_reference.to_canonical_dict()
        ),
        "configuration_references": [
            item.to_canonical_dict() for item in configuration_references
        ],
        "data_authority_mode": data_authority_mode.value,
        "evidence_qualification": evidence_qualification.value,
        "code_revision": code_revision,
        "created_at": canonical_datetime(created_at),
        "limitations": list(limitations),
    }


def _references(
    references: tuple[ValidationArtifactReference, ...],
) -> tuple[ValidationArtifactReference, ...]:
    keyed = {
        (item.artifact_kind, str(item.artifact_id), item.content_hash): item
        for item in references
    }
    return tuple(keyed[key] for key in sorted(keyed))


__all__ = [
    "HISTORICAL_RESEARCH_COMMAND_SCHEMA",
    "HistoricalResearchCommand",
]
