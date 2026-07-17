"""Rehearsal-scoped future path evidence for Entry Target materialization.

These contracts describe future market observations. They do not contain Entry outcomes,
policies, proposals, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    FinalizationTime,
)


def _require_symbol(symbol: str) -> None:
    if (
        not isinstance(symbol, str)
        or not symbol.strip()
        or symbol != symbol.strip()
    ):
        raise ValueError("symbol must be a non-empty trimmed string")


def _require_text(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_positive_finite(label: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _require_dataset_id(label: str, value: DatasetId) -> None:
    if not isinstance(value, DatasetId):
        raise TypeError(f"{label} must be a DatasetId")


def _evidence_id(prefix: str, payload: dict[str, object]) -> ArtifactId:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return ArtifactId(f"{prefix}-{digest[:24]}")


@dataclass(frozen=True, slots=True)
class RehearsalEntryReferenceEvidence:
    """Explicit 14:55 reference-price evidence for Entry Target materialization."""

    symbol: str
    decision_time: DecisionTime
    reference_price: float
    price_adjustment_basis: str
    available_at: AvailabilityTime
    source_dataset_id: DatasetId
    evidence_convention: str

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be a DecisionTime")
        _require_positive_finite("reference_price", self.reference_price)
        _require_text("price_adjustment_basis", self.price_adjustment_basis)
        if not isinstance(self.available_at, AvailabilityTime):
            raise TypeError("available_at must be an AvailabilityTime")
        if self.available_at.value > self.decision_time.value:
            raise ValueError("entry reference evidence must be available by decision_time")
        _require_dataset_id("source_dataset_id", self.source_dataset_id)
        _require_text("evidence_convention", self.evidence_convention)

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id(
            "entry-reference-evidence",
            {
                "schema_version": "entry-reference-evidence-v1",
                "symbol": self.symbol,
                "decision_time": self.decision_time.isoformat(),
                "reference_price": self.reference_price,
                "price_adjustment_basis": self.price_adjustment_basis,
                "available_at": self.available_at.isoformat(),
                "source_dataset_id": str(self.source_dataset_id),
                "evidence_convention": self.evidence_convention,
            },
        )


@dataclass(frozen=True, slots=True)
class RehearsalFuturePathSessionReadiness:
    """Declared future-evidence readiness deadline for one exchange session."""

    session_date: date
    evidence_ready_at: AvailabilityTime

    def __post_init__(self) -> None:
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        if not isinstance(self.evidence_ready_at, AvailabilityTime):
            raise TypeError("evidence_ready_at must be an AvailabilityTime")


@dataclass(frozen=True, slots=True)
class RehearsalFuturePathReadinessPolicy:
    source_dataset_id: DatasetId
    policy_convention: str
    effective_at: AvailabilityTime
    session_readiness: tuple[RehearsalFuturePathSessionReadiness, ...]

    def __post_init__(self) -> None:
        _require_dataset_id("source_dataset_id", self.source_dataset_id)
        _require_text("policy_convention", self.policy_convention)
        if not isinstance(self.effective_at, AvailabilityTime):
            raise TypeError("effective_at must be an AvailabilityTime")
        if not self.session_readiness:
            raise ValueError("session_readiness must not be empty")
        if any(
            not isinstance(item, RehearsalFuturePathSessionReadiness)
            for item in self.session_readiness
        ):
            raise TypeError(
                "session_readiness must contain RehearsalFuturePathSessionReadiness"
            )
        dates = tuple(item.session_date for item in self.session_readiness)
        if tuple(sorted(dates)) != dates or len(dates) != len(set(dates)):
            raise ValueError("readiness session dates must be chronological and unique")

    @property
    def policy_id(self) -> ArtifactId:
        return _evidence_id("future-path-readiness-policy", {"schema_version":"future-path-readiness-policy-v1","source_dataset_id":str(self.source_dataset_id),"policy_convention":self.policy_convention,"effective_at":self.effective_at.isoformat(),"session_readiness":[{"session_date":x.session_date.isoformat(),"evidence_ready_at":x.evidence_ready_at.isoformat()} for x in self.session_readiness]})


@dataclass(frozen=True, slots=True)
class RehearsalFuturePathCoverageAssertion:
    source_dataset_id: DatasetId
    available_at: AvailabilityTime
    coverage_convention: str
    covered_symbols: tuple[str, ...]
    coverage_through_session_date: date

    def __post_init__(self) -> None:
        _require_dataset_id("source_dataset_id", self.source_dataset_id)
        if not isinstance(self.available_at, AvailabilityTime):
            raise TypeError("available_at must be an AvailabilityTime")
        _require_text("coverage_convention", self.coverage_convention)
        for symbol in self.covered_symbols:
            _require_symbol(symbol)
        if tuple(sorted(self.covered_symbols)) != self.covered_symbols or len(self.covered_symbols) != len(set(self.covered_symbols)):
            raise ValueError("covered_symbols must be sorted and unique")
        if not isinstance(self.coverage_through_session_date, date):
            raise TypeError("coverage_through_session_date must be a date")

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id("future-path-coverage", {"schema_version":"future-path-coverage-v1","source_dataset_id":str(self.source_dataset_id),"available_at":self.available_at.isoformat(),"coverage_convention":self.coverage_convention,"covered_symbols":list(self.covered_symbols),"coverage_through_session_date":self.coverage_through_session_date.isoformat()})


def _require_evidence_times(
    available_at: AvailabilityTime,
    finalized_at: FinalizationTime,
) -> None:
    if not isinstance(available_at, AvailabilityTime):
        raise TypeError("available_at must be an AvailabilityTime")
    if not isinstance(finalized_at, FinalizationTime):
        raise TypeError("finalized_at must be a FinalizationTime")
    if available_at.value < finalized_at.value:
        raise ValueError("available_at must not precede finalized_at")


@dataclass(frozen=True, slots=True)
class RehearsalFutureDailyBar:
    """Finalized future daily OHLC evidence for path-dependent research Targets."""

    symbol: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    price_adjustment_basis: str
    source_dataset_id: DatasetId
    available_at: AvailabilityTime
    finalized_at: FinalizationTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        for label, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            _require_positive_finite(label, value)
        if self.low > self.high:
            raise ValueError("future daily OHLC requires low <= high")
        if not self.low <= self.open <= self.high:
            raise ValueError("future daily OHLC requires low <= open <= high")
        if not self.low <= self.close <= self.high:
            raise ValueError("future daily OHLC requires low <= close <= high")
        _require_text("price_adjustment_basis", self.price_adjustment_basis)
        _require_dataset_id("source_dataset_id", self.source_dataset_id)
        _require_evidence_times(self.available_at, self.finalized_at)

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id(
            "future-daily-bar-evidence",
            {
                "schema_version": "future-daily-bar-evidence-v1",
                "symbol": self.symbol,
                "session_date": self.session_date.isoformat(),
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "price_adjustment_basis": self.price_adjustment_basis,
                "source_dataset_id": str(self.source_dataset_id),
                "available_at": self.available_at.isoformat(),
                "finalized_at": self.finalized_at.isoformat(),
            },
        )


@dataclass(frozen=True, slots=True)
class RehearsalFutureSuspensionEvidence:
    """Explicit future session suspension state used when a daily bar is absent."""

    symbol: str
    session_date: date
    is_suspended: bool
    source_dataset_id: DatasetId
    available_at: AvailabilityTime
    finalized_at: FinalizationTime

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        if not isinstance(self.session_date, date):
            raise TypeError("session_date must be a date")
        if not isinstance(self.is_suspended, bool):
            raise TypeError("is_suspended must be boolean")
        _require_dataset_id("source_dataset_id", self.source_dataset_id)
        _require_evidence_times(self.available_at, self.finalized_at)

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id(
            "future-suspension-evidence",
            {
                "schema_version": "future-suspension-evidence-v1",
                "symbol": self.symbol,
                "session_date": self.session_date.isoformat(),
                "is_suspended": self.is_suspended,
                "source_dataset_id": str(self.source_dataset_id),
                "available_at": self.available_at.isoformat(),
                "finalized_at": self.finalized_at.isoformat(),
            },
        )
