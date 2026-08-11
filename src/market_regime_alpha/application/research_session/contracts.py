"""Execution-context contract shared by live and historical research sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    normalize_canonical_datetime,
    require_sha256,
    require_text,
)


RESEARCH_DECISION_SESSION_SCHEMA = "research-decision-session/v1"


class DataAuthorityMode(str, Enum):
    """Where the session's owner-resolved facts may come from."""

    RECORDED_LIVE_RESEARCH = "RECORDED_LIVE_RESEARCH"
    FREE_RESEARCH_ARCHIVE = "FREE_RESEARCH_ARCHIVE"
    QUALIFIED_FORMAL_PIT = "QUALIFIED_FORMAL_PIT"


class ResearchExecutionMode(str, Enum):
    LIVE_RESEARCH = "LIVE_RESEARCH"
    SHADOW = "SHADOW"
    HISTORICAL_RESEARCH = "HISTORICAL_RESEARCH"


class EvidenceQualification(str, Enum):
    EXPLORATORY_PIT_INCOMPLETE = "EXPLORATORY_PIT_INCOMPLETE"
    FORMAL_PIT_QUALIFIED = "FORMAL_PIT_QUALIFIED"


@dataclass(frozen=True, slots=True)
class ResearchDecisionSessionRequest:
    """Frozen differences between one live or historical decision session."""

    session_id: ArtifactId
    session_hash: str
    trading_date: date
    decision_time: datetime
    materialized_at: datetime
    data_authority_mode: DataAuthorityMode
    execution_mode: ResearchExecutionMode
    evidence_qualification: EvidenceQualification
    trading_calendar_id: ArtifactId
    trading_calendar_hash: str
    runtime_scope_policy_id: ArtifactId
    runtime_scope_policy_hash: str
    decision_policy_id: ArtifactId
    decision_policy_hash: str
    code_revision: str
    schema_version: str = RESEARCH_DECISION_SESSION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_DECISION_SESSION_SCHEMA:
            raise ValueError("unsupported Research Decision Session schema")
        for label, value in (
            ("trading_calendar_hash", self.trading_calendar_hash),
            ("runtime_scope_policy_hash", self.runtime_scope_policy_hash),
            ("decision_policy_hash", self.decision_policy_hash),
            ("session_hash", self.session_hash),
        ):
            require_sha256(label, value)
        require_text("code_revision", self.code_revision)
        decision_time = normalize_canonical_datetime(self.decision_time)
        materialized_at = normalize_canonical_datetime(self.materialized_at)
        if materialized_at < decision_time:
            raise ValueError("materialized_at cannot precede decision_time")
        if (
            self.data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE
            and self.evidence_qualification
            is EvidenceQualification.FORMAL_PIT_QUALIFIED
        ):
            raise ValueError("free Research data cannot claim Formal PIT")
        if (
            self.data_authority_mode is DataAuthorityMode.QUALIFIED_FORMAL_PIT
            and self.evidence_qualification
            is not EvidenceQualification.FORMAL_PIT_QUALIFIED
        ):
            raise ValueError("qualified Formal PIT authority requires Formal qualification")
        digest = canonical_hash(self.semantic_payload())
        if digest != self.session_hash:
            raise ValueError("Research Decision Session hash mismatch")
        expected = f"research-decision-session-{digest[7:31]}"
        if str(self.session_id) != expected:
            raise ValueError("Research Decision Session identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        trading_date: date,
        decision_time: datetime,
        materialized_at: datetime,
        data_authority_mode: DataAuthorityMode,
        execution_mode: ResearchExecutionMode,
        evidence_qualification: EvidenceQualification,
        trading_calendar_id: ArtifactId,
        trading_calendar_hash: str,
        runtime_scope_policy_id: ArtifactId,
        runtime_scope_policy_hash: str,
        decision_policy_id: ArtifactId,
        decision_policy_hash: str,
        code_revision: str,
    ) -> ResearchDecisionSessionRequest:
        values: dict[str, Any] = {
            "trading_date": trading_date,
            "decision_time": normalize_canonical_datetime(decision_time),
            "materialized_at": normalize_canonical_datetime(materialized_at),
            "data_authority_mode": data_authority_mode,
            "execution_mode": execution_mode,
            "evidence_qualification": evidence_qualification,
            "trading_calendar_id": trading_calendar_id,
            "trading_calendar_hash": trading_calendar_hash,
            "runtime_scope_policy_id": runtime_scope_policy_id,
            "runtime_scope_policy_hash": runtime_scope_policy_hash,
            "decision_policy_id": decision_policy_id,
            "decision_policy_hash": decision_policy_hash,
            "code_revision": code_revision,
        }
        digest = canonical_hash(_session_payload(**values))
        return cls(
            session_id=ArtifactId(f"research-decision-session-{digest[7:31]}"),
            session_hash=digest,
            **values,
        )

    def semantic_values(self) -> dict[str, Any]:
        """Return typed constructor inputs, useful for explicit replay mutations."""

        return {
            "trading_date": self.trading_date,
            "decision_time": self.decision_time,
            "materialized_at": self.materialized_at,
            "data_authority_mode": self.data_authority_mode,
            "execution_mode": self.execution_mode,
            "evidence_qualification": self.evidence_qualification,
            "trading_calendar_id": self.trading_calendar_id,
            "trading_calendar_hash": self.trading_calendar_hash,
            "runtime_scope_policy_id": self.runtime_scope_policy_id,
            "runtime_scope_policy_hash": self.runtime_scope_policy_hash,
            "decision_policy_id": self.decision_policy_id,
            "decision_policy_hash": self.decision_policy_hash,
            "code_revision": self.code_revision,
        }

    def semantic_payload(self) -> dict[str, Any]:
        return _session_payload(**self.semantic_values())

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "session_hash": self.session_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResearchDecisionSessionRequest:
        result = cls(
            session_id=ArtifactId(str(payload["session_id"])),
            session_hash=str(payload["session_hash"]),
            trading_date=date.fromisoformat(str(payload["trading_date"])),
            decision_time=datetime.fromisoformat(
                str(payload["decision_time"]).replace("Z", "+00:00")
            ),
            materialized_at=datetime.fromisoformat(
                str(payload["materialized_at"]).replace("Z", "+00:00")
            ),
            data_authority_mode=DataAuthorityMode(
                str(payload["data_authority_mode"])
            ),
            execution_mode=ResearchExecutionMode(str(payload["execution_mode"])),
            evidence_qualification=EvidenceQualification(
                str(payload["evidence_qualification"])
            ),
            trading_calendar_id=ArtifactId(str(payload["trading_calendar_id"])),
            trading_calendar_hash=str(payload["trading_calendar_hash"]),
            runtime_scope_policy_id=ArtifactId(
                str(payload["runtime_scope_policy_id"])
            ),
            runtime_scope_policy_hash=str(payload["runtime_scope_policy_hash"]),
            decision_policy_id=ArtifactId(str(payload["decision_policy_id"])),
            decision_policy_hash=str(payload["decision_policy_hash"]),
            code_revision=str(payload["code_revision"]),
            schema_version=str(payload["schema_version"]),
        )
        if set(payload) != set(result.to_canonical_dict()):
            raise ValueError("Research Decision Session fields mismatch")
        return result


def _session_payload(
    *,
    trading_date: date,
    decision_time: datetime,
    materialized_at: datetime,
    data_authority_mode: DataAuthorityMode,
    execution_mode: ResearchExecutionMode,
    evidence_qualification: EvidenceQualification,
    trading_calendar_id: ArtifactId,
    trading_calendar_hash: str,
    runtime_scope_policy_id: ArtifactId,
    runtime_scope_policy_hash: str,
    decision_policy_id: ArtifactId,
    decision_policy_hash: str,
    code_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": RESEARCH_DECISION_SESSION_SCHEMA,
        "trading_date": trading_date.isoformat(),
        "decision_time": canonical_datetime(decision_time),
        "materialized_at": canonical_datetime(materialized_at),
        "data_authority_mode": data_authority_mode.value,
        "execution_mode": execution_mode.value,
        "evidence_qualification": evidence_qualification.value,
        "trading_calendar_id": str(trading_calendar_id),
        "trading_calendar_hash": trading_calendar_hash,
        "runtime_scope_policy_id": str(runtime_scope_policy_id),
        "runtime_scope_policy_hash": runtime_scope_policy_hash,
        "decision_policy_id": str(decision_policy_id),
        "decision_policy_hash": decision_policy_hash,
        "code_revision": code_revision,
    }


__all__ = [
    "DataAuthorityMode",
    "EvidenceQualification",
    "RESEARCH_DECISION_SESSION_SCHEMA",
    "ResearchDecisionSessionRequest",
    "ResearchExecutionMode",
]
