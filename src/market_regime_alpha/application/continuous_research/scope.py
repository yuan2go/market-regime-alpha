"""Thin CRR adapter over existing Universe, Eligibility, and Orderability contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_unique_text,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_artifacts import (
    HistoricalTradingEligibilityArtifact,
)
from market_regime_alpha.universe.orderability import (
    OrderabilityStatus,
    ResearchOrderabilityAssessment,
)
from market_regime_alpha.universe.request_scoped import RequestScopedUniverse


CONTINUOUS_RESEARCH_SCOPE_SCHEMA = "continuous-research-scope-v1"


@dataclass(frozen=True, slots=True)
class ContinuousResearchScopeRecord:
    symbol: str
    universe_included: bool
    universe_reason_codes: tuple[str, ...]
    eligibility_status: TradingEligibilityStatus
    eligibility_reason_codes: tuple[str, ...]
    eligibility_evidence_found: bool
    orderability_status: OrderabilityStatus
    orderability_reason_codes: tuple[str, ...]
    orderability_evidence_found: bool
    research_candidate_eligible: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, reasons in (
            ("universe", self.universe_reason_codes),
            ("eligibility", self.eligibility_reason_codes),
            ("orderability", self.orderability_reason_codes),
            ("scope", self.reason_codes),
        ):
            require_unique_text(f"{label} reason", reasons)
            if reasons != tuple(sorted(reasons)):
                raise ValueError(f"{label} reasons must be sorted")
        expected = bool(
            self.universe_included
            and self.eligibility_status is TradingEligibilityStatus.ELIGIBLE
            and self.orderability_status
            is OrderabilityStatus.ORDERABLE_FOR_RESEARCH
        )
        if self.research_candidate_eligible is not expected:
            raise ValueError("research Candidate eligibility must fail closed")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "universe_included": self.universe_included,
            "universe_reason_codes": list(self.universe_reason_codes),
            "eligibility_status": self.eligibility_status.value,
            "eligibility_reason_codes": list(self.eligibility_reason_codes),
            "eligibility_evidence_found": self.eligibility_evidence_found,
            "orderability_status": self.orderability_status.value,
            "orderability_reason_codes": list(self.orderability_reason_codes),
            "orderability_evidence_found": self.orderability_evidence_found,
            "research_candidate_eligible": self.research_candidate_eligible,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class ContinuousResearchScope:
    schema_version: str
    scope_id: ArtifactId
    content_hash: str
    decision_time: DecisionTime
    request_scoped_universe_id: ArtifactId
    request_scoped_universe_hash: str
    eligibility_artifact_id: ArtifactId
    eligibility_policy_version: str
    exact_eligibility_snapshot_found: bool
    records: tuple[ContinuousResearchScopeRecord, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTINUOUS_RESEARCH_SCOPE_SCHEMA:
            raise ValueError("unsupported Continuous Research Scope schema")
        require_sha256("content_hash", self.content_hash)
        require_sha256(
            "request_scoped_universe_hash", self.request_scoped_universe_hash
        )
        symbols = tuple(record.symbol for record in self.records)
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Continuous Research Scope records must be unique and sorted")
        require_unique_text("Continuous Research Scope limitation", self.limitations)
        if self.limitations != tuple(sorted(self.limitations)):
            raise ValueError("Continuous Research Scope limitations must be sorted")
        for required in (
            "ENTRY_BLOCKED",
            "NO_ORDER_AUTHORITY",
            "REQUEST_SCOPED_UNIVERSE",
        ):
            if required not in self.limitations:
                raise ValueError("Continuous Research Scope authority ceiling is incomplete")
        self.verify_identity()

    @property
    def entry_authority_granted(self) -> bool:
        return False

    @property
    def candidate_symbols(self) -> tuple[str, ...]:
        return tuple(
            item.symbol for item in self.records if item.research_candidate_eligible
        )

    def record_for(self, symbol: str) -> ContinuousResearchScopeRecord:
        for record in self.records:
            if record.symbol == symbol:
                return record
        raise KeyError(symbol)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": CONTINUOUS_RESEARCH_SCOPE_SCHEMA,
            "decision_time": canonical_datetime(self.decision_time.value),
            "request_scoped_universe_id": str(self.request_scoped_universe_id),
            "request_scoped_universe_hash": self.request_scoped_universe_hash,
            "eligibility_artifact_id": str(self.eligibility_artifact_id),
            "eligibility_policy_version": self.eligibility_policy_version,
            "exact_eligibility_snapshot_found": self.exact_eligibility_snapshot_found,
            "records": [item.to_canonical_dict() for item in self.records],
            "limitations": list(self.limitations),
        }

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Continuous Research Scope content hash mismatch")
        expected = f"continuous-research-scope-{digest.split(':', 1)[1][:24]}"
        if str(self.scope_id) != expected:
            raise ValueError("Continuous Research Scope identity mismatch")


def prepare_continuous_research_scope(
    *,
    request_scoped_universe: RequestScopedUniverse,
    eligibility_artifact: HistoricalTradingEligibilityArtifact,
    decision_time: DecisionTime,
    orderability_assessments: Mapping[str, ResearchOrderabilityAssessment],
) -> ContinuousResearchScope:
    """Compose current contracts without redefining their policy semantics."""

    request_scoped_universe.verify_identity()
    if not isinstance(eligibility_artifact, HistoricalTradingEligibilityArtifact):
        raise TypeError(
            "eligibility_artifact must be HistoricalTradingEligibilityArtifact"
        )
    if not isinstance(decision_time, DecisionTime):
        raise TypeError("decision_time must be a DecisionTime")
    requested = set(request_scoped_universe.requested_symbols)
    if any(symbol not in requested for symbol in orderability_assessments):
        raise ValueError("Orderability assessment is outside the request scope")
    try:
        snapshot = eligibility_artifact.snapshot_for_decision_time(decision_time)
    except KeyError:
        snapshot = None
    eligibility_by_symbol = (
        {} if snapshot is None else {item.symbol: item for item in snapshot.records}
    )
    records: list[ContinuousResearchScopeRecord] = []
    for universe_record in request_scoped_universe.records:
        eligibility = eligibility_by_symbol.get(universe_record.symbol)
        eligibility_reasons: tuple[str, ...]
        if eligibility is None:
            eligibility_status = TradingEligibilityStatus.UNKNOWN
            eligibility_reasons = (
                "ELIGIBILITY_SNAPSHOT_MISSING",
            ) if snapshot is None else ("ELIGIBILITY_RECORD_MISSING",)
        else:
            eligibility_status = eligibility.status
            eligibility_reasons = tuple(sorted(eligibility.reasons))
        orderability = orderability_assessments.get(universe_record.symbol)
        orderability_reasons: tuple[str, ...]
        if orderability is None:
            orderability_status = OrderabilityStatus.ORDERABILITY_UNKNOWN
            orderability_reasons = ("ORDERABILITY_EVIDENCE_MISSING",)
        else:
            if orderability.symbol != universe_record.symbol:
                raise ValueError("Orderability assessment symbol mismatch")
            orderability.verify_identity()
            orderability_status = orderability.status
            orderability_reasons = orderability.reason_codes
        candidate_eligible = bool(
            universe_record.included
            and eligibility_status is TradingEligibilityStatus.ELIGIBLE
            and orderability_status is OrderabilityStatus.ORDERABLE_FOR_RESEARCH
        )
        combined_reasons = set(universe_record.reason_codes)
        combined_reasons.update(eligibility_reasons)
        combined_reasons.update(orderability_reasons)
        combined_reasons.add(
            "RESEARCH_CANDIDATE_ELIGIBLE"
            if candidate_eligible
            else "RESEARCH_CANDIDATE_BLOCKED"
        )
        if not universe_record.included:
            combined_reasons.add("REQUEST_SCOPE_UNIVERSE_EXCLUDED")
        records.append(
            ContinuousResearchScopeRecord(
                symbol=universe_record.symbol,
                universe_included=universe_record.included,
                universe_reason_codes=tuple(sorted(universe_record.reason_codes)),
                eligibility_status=eligibility_status,
                eligibility_reason_codes=eligibility_reasons,
                eligibility_evidence_found=eligibility is not None,
                orderability_status=orderability_status,
                orderability_reason_codes=orderability_reasons,
                orderability_evidence_found=orderability is not None,
                research_candidate_eligible=candidate_eligible,
                reason_codes=tuple(sorted(combined_reasons)),
            )
        )
    values: dict[str, Any] = {
        "decision_time": decision_time,
        "request_scoped_universe_id": ArtifactId(
            str(request_scoped_universe.universe_id)
        ),
        "request_scoped_universe_hash": request_scoped_universe.content_hash,
        "eligibility_artifact_id": eligibility_artifact.artifact_id,
        "eligibility_policy_version": eligibility_artifact.policy_version,
        "exact_eligibility_snapshot_found": snapshot is not None,
        "records": tuple(records),
        "limitations": (
            "ELIGIBILITY_SOURCE_MANIFEST_NOT_EMBEDDED",
            "ENTRY_BLOCKED",
            "NO_ORDER_AUTHORITY",
            "REQUEST_SCOPED_UNIVERSE",
        ),
    }
    payload = {
        "schema_version": CONTINUOUS_RESEARCH_SCOPE_SCHEMA,
        "decision_time": canonical_datetime(decision_time.value),
        "request_scoped_universe_id": str(values["request_scoped_universe_id"]),
        "request_scoped_universe_hash": values["request_scoped_universe_hash"],
        "eligibility_artifact_id": str(values["eligibility_artifact_id"]),
        "eligibility_policy_version": values["eligibility_policy_version"],
        "exact_eligibility_snapshot_found": values[
            "exact_eligibility_snapshot_found"
        ],
        "records": [item.to_canonical_dict() for item in records],
        "limitations": list(values["limitations"]),
    }
    digest = canonical_hash(payload)
    return ContinuousResearchScope(
        schema_version=CONTINUOUS_RESEARCH_SCOPE_SCHEMA,
        scope_id=ArtifactId(
            f"continuous-research-scope-{digest.split(':', 1)[1][:24]}"
        ),
        content_hash=digest,
        **values,
    )


__all__ = [
    "CONTINUOUS_RESEARCH_SCOPE_SCHEMA",
    "ContinuousResearchScope",
    "ContinuousResearchScopeRecord",
    "prepare_continuous_research_scope",
]
