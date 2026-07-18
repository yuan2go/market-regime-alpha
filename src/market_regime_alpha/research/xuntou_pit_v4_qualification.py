"""Evidence-derived qualification receipt for Xuntou PIT v4."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_regime_alpha.research.prr_artifact_schemas import canonical_identity_hash
from market_regime_alpha.research.xuntou_pit_v4_contract import (
    QUALIFIED_PIT_MARKET_ARTIFACT_SCHEMA_VERSION,
    QualifiedPITMarketArtifact,
    XuntouPITSourceArtifact,
)


@dataclass(frozen=True, slots=True)
class PITEvidenceQualification:
    schema_version: str
    historical_membership_complete: bool
    security_master_complete: bool
    st_history_complete: bool
    suspension_history_complete: bool
    orderability_complete: bool
    liquidity_unit_verified: bool
    bar_finality_verified: bool
    availability_verified: bool
    evaluation_path_complete: bool
    pit_correct_for_scope: bool
    reasons: tuple[str, ...]
    input_declaration_ignored: bool

    @property
    def qualification_id(self) -> str:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return canonical_identity_hash(payload)

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["qualification_id"] = self.qualification_id
        return payload


def derive_pit_qualification(
    *,
    historical_membership_complete: bool,
    security_master_complete: bool,
    st_history_complete: bool,
    suspension_history_complete: bool,
    orderability_complete: bool,
    liquidity_unit_verified: bool,
    bar_finality_verified: bool,
    availability_verified: bool,
    evaluation_path_complete: bool,
    membership_sources: tuple[str, ...] = (),
    input_declared_pit_correct: bool | None = None,
) -> PITEvidenceQualification:
    checks = (
        (historical_membership_complete, "HISTORICAL_MEMBERSHIP_INCOMPLETE"),
        (security_master_complete, "SECURITY_MASTER_INCOMPLETE"),
        (st_history_complete, "ST_HISTORY_INCOMPLETE"),
        (suspension_history_complete, "SUSPENSION_HISTORY_INCOMPLETE"),
        (orderability_complete, "DECISION_TIME_ORDERABILITY_INCOMPLETE"),
        (liquidity_unit_verified, "ABSOLUTE_LIQUIDITY_THRESHOLD_NOT_QUALIFIED"),
        (bar_finality_verified, "BAR_FINALITY_UNVERIFIED"),
        (availability_verified, "AVAILABILITY_TIME_UNVERIFIED"),
        (evaluation_path_complete, "NEXT_SESSION_1030_EVIDENCE_INCOMPLETE"),
    )
    reasons = [reason for passed, reason in checks if not passed]
    if any(source in {"CURRENT_WATCHLIST_BACKFILL", "CURRENT_MEMBERSHIP_BACKFILL"} for source in membership_sources):
        reasons.append("CURRENT_MEMBERSHIP_BACKFILL_REJECTED")
    return PITEvidenceQualification(
        schema_version="xuntou-pit-evidence-qualification-v4",
        historical_membership_complete=historical_membership_complete,
        security_master_complete=security_master_complete,
        st_history_complete=st_history_complete,
        suspension_history_complete=suspension_history_complete,
        orderability_complete=orderability_complete,
        liquidity_unit_verified=liquidity_unit_verified,
        bar_finality_verified=bar_finality_verified,
        availability_verified=availability_verified,
        evaluation_path_complete=evaluation_path_complete,
        pit_correct_for_scope=not reasons,
        reasons=tuple(reasons),
        input_declaration_ignored=input_declared_pit_correct is not None,
    )


def build_qualified_pit_market_artifact(
    *,
    source: XuntouPITSourceArtifact,
    qualification: PITEvidenceQualification,
) -> QualifiedPITMarketArtifact:
    if source.evidence_classification == "TEST_ONLY_NOT_RESEARCH_EVIDENCE":
        raise ValueError("test-only fixture cannot produce a qualified provider Artifact")
    if not qualification.pit_correct_for_scope:
        raise ValueError("unqualified evidence cannot produce a qualified provider Artifact")
    provider_artifact_id = canonical_identity_hash(
        {
            "schema_version": QUALIFIED_PIT_MARKET_ARTIFACT_SCHEMA_VERSION,
            "source_content_hash": source.content_hash,
            "qualification_id": qualification.qualification_id,
        }
    )
    return QualifiedPITMarketArtifact(
        QUALIFIED_PIT_MARKET_ARTIFACT_SCHEMA_VERSION,
        source,
        qualification.qualification_id,
        provider_artifact_id,
        "CONTROLLED_REPLICATION_INPUT",
    )
