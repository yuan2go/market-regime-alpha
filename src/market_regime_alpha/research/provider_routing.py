"""Authority-aware provider routing for R5 Candidate research.

The router consumes immutable preflight reports. It performs no provider I/O and never
interprets an empty Candidate result as a reason to change data source.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json

from market_regime_alpha.data import DataEligibility


PROVIDER_SELECTION_POLICY_VERSION = "R5_CANDIDATE_DATA_SOURCE_SELECTION_V1"
XUNTOU_PRIMARY_UNAVAILABLE = "XUNTOU_PRIMARY_UNAVAILABLE"

_ELIGIBILITY_RANK = {
    DataEligibility.UNQUALIFIED: 0,
    DataEligibility.EXPLORATORY: 1,
    DataEligibility.REHEARSAL: 2,
    DataEligibility.FORMAL_RESEARCH: 3,
}


class CandidateDataSource(str, Enum):
    """Whole-run data sources supported by the first WP-3 routing policy."""

    XUNTOU = "XUNTOU"
    TENCENT_COMPOSITE = "TENCENT_COMPOSITE"


class CandidateRunSourceMode(str, Enum):
    """Caller-selected source-routing mode."""

    AUTO = "AUTO"
    XUNTOU = "XUNTOU"
    TENCENT = "TENCENT"


class ProviderAvailabilityStatus(str, Enum):
    """Preflight result before source selection."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class ProviderSelectionDisposition(str, Enum):
    """Outcome of one provider-selection attempt."""

    SELECTED = "SELECTED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    AUTHORITY_REJECTED = "AUTHORITY_REJECTED"


class ProviderSelectionReasonCode(str, Enum):
    """Stable reason attached to a provider-selection attempt."""

    AVAILABLE_AND_AUTHORIZED = "AVAILABLE_AND_AUTHORIZED"
    PREFLIGHT_UNAVAILABLE = "PREFLIGHT_UNAVAILABLE"
    PREFLIGHT_INVALID = "PREFLIGHT_INVALID"
    MAXIMUM_ELIGIBILITY_BELOW_REQUEST = "MAXIMUM_ELIGIBILITY_BELOW_REQUEST"


class ProviderRoutingErrorCode(str, Enum):
    """Stable failure codes for caller-visible routing errors."""

    REQUIRED_SOURCE_UNAVAILABLE = "PROVIDER_ROUTE_REQUIRED_SOURCE_UNAVAILABLE"
    SOURCE_INVALID = "PROVIDER_ROUTE_SOURCE_INVALID"
    AUTHORITY_UNSUPPORTED = "PROVIDER_ROUTE_AUTHORITY_UNSUPPORTED"
    NO_ELIGIBLE_SOURCE = "PROVIDER_ROUTE_NO_ELIGIBLE_SOURCE"


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_unique_strings(label: str, values: tuple[str, ...]) -> None:
    for value in values:
        _require_non_empty(label, value)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


@dataclass(frozen=True, slots=True)
class ProviderCapabilityReport:
    """Provider preflight facts consumed by the pure router."""

    source: CandidateDataSource
    availability_status: ProviderAvailabilityStatus
    maximum_data_eligibility: DataEligibility
    supported_evidence: tuple[str, ...]
    unsupported_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    input_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, CandidateDataSource):
            raise TypeError("source must be a CandidateDataSource")
        if not isinstance(self.availability_status, ProviderAvailabilityStatus):
            raise TypeError("availability_status must be a ProviderAvailabilityStatus")
        if not isinstance(self.maximum_data_eligibility, DataEligibility):
            raise TypeError("maximum_data_eligibility must be a DataEligibility")
        _require_unique_strings("supported_evidence", self.supported_evidence)
        _require_unique_strings("unsupported_evidence", self.unsupported_evidence)
        _require_unique_strings("limitations", self.limitations)
        _require_non_empty("input_identity", self.input_identity)
        overlap = set(self.supported_evidence) & set(self.unsupported_evidence)
        if overlap:
            raise ValueError("supported_evidence and unsupported_evidence must not overlap")
        ceiling = (
            DataEligibility.REHEARSAL
            if self.source is CandidateDataSource.XUNTOU
            else DataEligibility.EXPLORATORY
        )
        if _ELIGIBILITY_RANK[self.maximum_data_eligibility] > _ELIGIBILITY_RANK[ceiling]:
            raise ValueError(
                f"{self.source.value} maximum_data_eligibility cannot exceed {ceiling.value}"
            )


@dataclass(frozen=True, slots=True)
class ProviderSelectionAttempt:
    """One checked provider and the exact reason it was accepted or rejected."""

    source: CandidateDataSource
    disposition: ProviderSelectionDisposition
    reason_code: ProviderSelectionReasonCode
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, CandidateDataSource):
            raise TypeError("source must be a CandidateDataSource")
        if not isinstance(self.disposition, ProviderSelectionDisposition):
            raise TypeError("disposition must be a ProviderSelectionDisposition")
        if not isinstance(self.reason_code, ProviderSelectionReasonCode):
            raise TypeError("reason_code must be a ProviderSelectionReasonCode")
        _require_non_empty("detail", self.detail)


@dataclass(frozen=True, slots=True)
class ProviderSelectionDecision:
    """Deterministic whole-provider selection for one Candidate run."""

    selected_source: CandidateDataSource
    selected_data_eligibility: DataEligibility
    attempts: tuple[ProviderSelectionAttempt, ...]
    limitations: tuple[str, ...]
    policy_version: str
    decision_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.selected_source, CandidateDataSource):
            raise TypeError("selected_source must be a CandidateDataSource")
        if not isinstance(self.selected_data_eligibility, DataEligibility):
            raise TypeError("selected_data_eligibility must be a DataEligibility")
        if not self.attempts:
            raise ValueError("attempts must not be empty")
        if self.attempts[-1].disposition is not ProviderSelectionDisposition.SELECTED:
            raise ValueError("the final attempt must select the chosen source")
        if self.attempts[-1].source is not self.selected_source:
            raise ValueError("the selected source must match the final attempt")
        _require_unique_strings("limitations", self.limitations)
        _require_non_empty("policy_version", self.policy_version)
        _require_non_empty("decision_id", self.decision_id)
        if not self.decision_id.startswith("provider-selection:sha256:"):
            raise ValueError("decision_id must use provider-selection:sha256 identity")
        if self.selected_data_eligibility is DataEligibility.FORMAL_RESEARCH:
            raise ValueError("provider routing cannot emit FORMAL_RESEARCH")


class ProviderRoutingError(RuntimeError):
    """A fail-closed provider routing error with retained attempt evidence."""

    def __init__(
        self,
        code: ProviderRoutingErrorCode,
        message: str,
        *,
        attempts: tuple[ProviderSelectionAttempt, ...] = (),
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.attempts = attempts


def select_candidate_data_source(
    *,
    mode: CandidateRunSourceMode,
    minimum_eligibility: DataEligibility,
    xuntou: ProviderCapabilityReport,
    tencent: ProviderCapabilityReport,
) -> ProviderSelectionDecision:
    """Select one complete provider backend without network I/O or field mixing."""

    if not isinstance(mode, CandidateRunSourceMode):
        raise TypeError("mode must be a CandidateRunSourceMode")
    if not isinstance(minimum_eligibility, DataEligibility):
        raise TypeError("minimum_eligibility must be a DataEligibility")
    if xuntou.source is not CandidateDataSource.XUNTOU:
        raise ValueError("xuntou report must describe CandidateDataSource.XUNTOU")
    if tencent.source is not CandidateDataSource.TENCENT_COMPOSITE:
        raise ValueError("tencent report must describe CandidateDataSource.TENCENT_COMPOSITE")
    if minimum_eligibility is DataEligibility.FORMAL_RESEARCH:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED,
            "WP-3 provider routes cannot satisfy FORMAL_RESEARCH authority",
        )

    if mode is CandidateRunSourceMode.XUNTOU:
        return _select_explicit(
            report=xuntou,
            mode=mode,
            minimum_eligibility=minimum_eligibility,
            xuntou=xuntou,
            tencent=tencent,
        )
    if mode is CandidateRunSourceMode.TENCENT:
        return _select_explicit(
            report=tencent,
            mode=mode,
            minimum_eligibility=minimum_eligibility,
            xuntou=xuntou,
            tencent=tencent,
        )

    first_attempt = _attempt_report(xuntou, minimum_eligibility)
    if first_attempt.disposition is ProviderSelectionDisposition.SELECTED:
        return _decision(
            mode=mode,
            minimum_eligibility=minimum_eligibility,
            xuntou=xuntou,
            tencent=tencent,
            report=xuntou,
            attempts=(first_attempt,),
            limitations=xuntou.limitations,
        )
    if first_attempt.disposition is ProviderSelectionDisposition.INVALID:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.SOURCE_INVALID,
            "the supplied Xuntou input is invalid; auxiliary fallback is forbidden",
            attempts=(first_attempt,),
        )
    if first_attempt.disposition is ProviderSelectionDisposition.AUTHORITY_REJECTED:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED,
            first_attempt.detail,
            attempts=(first_attempt,),
        )

    second_attempt = _attempt_report(tencent, minimum_eligibility)
    attempts = (first_attempt, second_attempt)
    if second_attempt.disposition is ProviderSelectionDisposition.SELECTED:
        limitations = _unique(
            (XUNTOU_PRIMARY_UNAVAILABLE, *xuntou.limitations, *tencent.limitations)
        )
        return _decision(
            mode=mode,
            minimum_eligibility=minimum_eligibility,
            xuntou=xuntou,
            tencent=tencent,
            report=tencent,
            attempts=attempts,
            limitations=limitations,
        )
    if second_attempt.disposition is ProviderSelectionDisposition.INVALID:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.SOURCE_INVALID,
            second_attempt.detail,
            attempts=attempts,
        )
    if second_attempt.disposition is ProviderSelectionDisposition.AUTHORITY_REJECTED:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED,
            second_attempt.detail,
            attempts=attempts,
        )
    raise ProviderRoutingError(
        ProviderRoutingErrorCode.NO_ELIGIBLE_SOURCE,
        "neither Xuntou nor Tencent composite is available",
        attempts=attempts,
    )


def _select_explicit(
    *,
    report: ProviderCapabilityReport,
    mode: CandidateRunSourceMode,
    minimum_eligibility: DataEligibility,
    xuntou: ProviderCapabilityReport,
    tencent: ProviderCapabilityReport,
) -> ProviderSelectionDecision:
    attempt = _attempt_report(report, minimum_eligibility)
    attempts = (attempt,)
    if attempt.disposition is ProviderSelectionDisposition.INVALID:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.SOURCE_INVALID,
            attempt.detail,
            attempts=attempts,
        )
    if attempt.disposition is ProviderSelectionDisposition.UNAVAILABLE:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.REQUIRED_SOURCE_UNAVAILABLE,
            attempt.detail,
            attempts=attempts,
        )
    if attempt.disposition is ProviderSelectionDisposition.AUTHORITY_REJECTED:
        raise ProviderRoutingError(
            ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED,
            attempt.detail,
            attempts=attempts,
        )
    return _decision(
        mode=mode,
        minimum_eligibility=minimum_eligibility,
        xuntou=xuntou,
        tencent=tencent,
        report=report,
        attempts=attempts,
        limitations=report.limitations,
    )


def _attempt_report(
    report: ProviderCapabilityReport,
    minimum_eligibility: DataEligibility,
) -> ProviderSelectionAttempt:
    if report.availability_status is ProviderAvailabilityStatus.INVALID:
        return ProviderSelectionAttempt(
            source=report.source,
            disposition=ProviderSelectionDisposition.INVALID,
            reason_code=ProviderSelectionReasonCode.PREFLIGHT_INVALID,
            detail=f"{report.source.value} preflight classified the input as INVALID",
        )
    if report.availability_status is ProviderAvailabilityStatus.UNAVAILABLE:
        return ProviderSelectionAttempt(
            source=report.source,
            disposition=ProviderSelectionDisposition.UNAVAILABLE,
            reason_code=ProviderSelectionReasonCode.PREFLIGHT_UNAVAILABLE,
            detail=f"{report.source.value} is unavailable for this run",
        )
    if not _eligibility_at_least(report.maximum_data_eligibility, minimum_eligibility):
        return ProviderSelectionAttempt(
            source=report.source,
            disposition=ProviderSelectionDisposition.AUTHORITY_REJECTED,
            reason_code=ProviderSelectionReasonCode.MAXIMUM_ELIGIBILITY_BELOW_REQUEST,
            detail=(
                f"{report.source.value} is capped at "
                f"{report.maximum_data_eligibility.value}, below requested "
                f"{minimum_eligibility.value}"
            ),
        )
    return ProviderSelectionAttempt(
        source=report.source,
        disposition=ProviderSelectionDisposition.SELECTED,
        reason_code=ProviderSelectionReasonCode.AVAILABLE_AND_AUTHORIZED,
        detail=(
            f"{report.source.value} is available with maximum authority "
            f"{report.maximum_data_eligibility.value}"
        ),
    )


def _decision(
    *,
    mode: CandidateRunSourceMode,
    minimum_eligibility: DataEligibility,
    xuntou: ProviderCapabilityReport,
    tencent: ProviderCapabilityReport,
    report: ProviderCapabilityReport,
    attempts: tuple[ProviderSelectionAttempt, ...],
    limitations: tuple[str, ...],
) -> ProviderSelectionDecision:
    normalized_limitations = _unique(limitations)
    payload = {
        "attempts": [_attempt_payload(item) for item in attempts],
        "minimum_eligibility": minimum_eligibility.value,
        "mode": mode.value,
        "policy_version": PROVIDER_SELECTION_POLICY_VERSION,
        "reports": [_report_payload(xuntou), _report_payload(tencent)],
        "selected_data_eligibility": report.maximum_data_eligibility.value,
        "selected_source": report.source.value,
        "limitations": list(normalized_limitations),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    decision_id = f"provider-selection:sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
    return ProviderSelectionDecision(
        selected_source=report.source,
        selected_data_eligibility=report.maximum_data_eligibility,
        attempts=attempts,
        limitations=normalized_limitations,
        policy_version=PROVIDER_SELECTION_POLICY_VERSION,
        decision_id=decision_id,
    )


def _report_payload(report: ProviderCapabilityReport) -> dict[str, object]:
    return {
        "availability_status": report.availability_status.value,
        "input_identity": report.input_identity,
        "limitations": list(report.limitations),
        "maximum_data_eligibility": report.maximum_data_eligibility.value,
        "source": report.source.value,
        "supported_evidence": list(report.supported_evidence),
        "unsupported_evidence": list(report.unsupported_evidence),
    }


def _attempt_payload(attempt: ProviderSelectionAttempt) -> dict[str, str]:
    return {
        "detail": attempt.detail,
        "disposition": attempt.disposition.value,
        "reason_code": attempt.reason_code.value,
        "source": attempt.source.value,
    }


def _eligibility_at_least(actual: DataEligibility, required: DataEligibility) -> bool:
    return _ELIGIBILITY_RANK[actual] >= _ELIGIBILITY_RANK[required]


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
