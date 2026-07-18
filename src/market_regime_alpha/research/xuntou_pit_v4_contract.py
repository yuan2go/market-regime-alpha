"""Qualified Xuntou PIT validation evidence contracts.

These contracts model research evidence, not historical fill proof or production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import math


XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION = "xuntou-pit-validation-bundle-v4"
XUNTOU_PIT_V4_MAPPING_CONTRACT_ID = "xuntou-pit-validation-field-mapping-v4"
QUALIFIED_PIT_MARKET_ARTIFACT_SCHEMA_VERSION = "qualified-pit-market-artifact-v1"


class ResearchOrderabilityStatus(str, Enum):
    RESEARCH_ORDERABLE = "RESEARCH_ORDERABLE"
    NOT_ORDERABLE = "NOT_ORDERABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class XuntouPITSourceArtifact:
    provider: str
    product: str
    contract_version: str
    retrieved_at: datetime
    export_started_at: datetime
    export_completed_at: datetime
    content_hash: str
    locator_role: str
    entitlement_class: str
    runtime_version: str
    xtquant_version: str
    timezone: str
    evidence_classification: str

    def __post_init__(self) -> None:
        if self.provider != "XUNTOU" or self.product != "XTQUANT":
            raise ValueError("Xuntou PIT source identity mismatch")
        if self.contract_version != XUNTOU_PIT_V4_BUNDLE_SCHEMA_VERSION:
            raise ValueError("Xuntou PIT source contract mismatch")
        if not self.content_hash.startswith("sha256:") or len(self.content_hash) != 71:
            raise ValueError("Xuntou PIT source content hash is invalid")
        if not self.export_started_at <= self.export_completed_at <= self.retrieved_at:
            raise ValueError("Xuntou PIT export timestamps are inconsistent")
        if self.timezone != "Asia/Shanghai":
            raise ValueError("Xuntou PIT timezone must be Asia/Shanghai")
        if self.locator_role != "EXTERNAL_IMMUTABLE_INPUT":
            raise ValueError("Xuntou PIT source locator must be non-semantic")


@dataclass(frozen=True, slots=True)
class AmountUnitContract:
    currency: str
    unit: str
    scale: float
    aggregation: str
    adjustment_basis: str
    provider_field: str
    evidence_source: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("amount unit scale must be finite and positive")

    @property
    def absolute_threshold_qualified(self) -> bool:
        return (
            self.currency == "CNY"
            and self.unit == "YUAN"
            and self.scale == 1.0
            and self.aggregation == "SUM_NATIVE_PERIOD_AMOUNT"
            and self.adjustment_basis == "NONE"
            and self.provider_field == "amount"
            and bool(self.evidence_source)
        )


@dataclass(frozen=True, slots=True)
class SecurityMasterEvidence:
    symbol: str
    exchange: str
    instrument_type: str
    listing_date: date
    delisting_date: date | None
    effective_from: datetime
    effective_to: datetime | None
    available_at: datetime
    lookup_complete: bool
    source_reference: str


@dataclass(frozen=True, slots=True)
class HistoricalUniverseMembershipEvidence:
    as_of_date: date
    symbol: str
    is_member: bool
    effective_from: datetime
    effective_to: datetime | None
    membership_source: str
    available_at: datetime
    lookup_complete: bool
    source_artifact_id: str


@dataclass(frozen=True, slots=True)
class HistoricalStatusIntervalEvidence:
    symbol: str
    status_type: str
    effective_from: datetime
    effective_to: datetime | None
    available_at: datetime
    lookup_complete: bool
    source_reference: str


@dataclass(frozen=True, slots=True)
class TradingStatusEvidence:
    decision_time: datetime
    symbol: str
    trading_status: str
    suspension_status: str
    available_at: datetime
    lookup_complete: bool
    source_reference: str


@dataclass(frozen=True, slots=True)
class OrderabilityEvidence:
    decision_time: datetime
    symbol: str
    reference_price: float | None
    best_ask_price: float | None
    best_ask_volume: float | None
    best_bid_price: float | None
    best_bid_volume: float | None
    limit_up_price: float | None
    limit_down_price: float | None
    trading_status: str
    suspension_status: str
    quote_observed_at: datetime | None
    available_at: datetime
    snapshot_finalized: bool
    orderability_status: ResearchOrderabilityStatus
    orderability_reason: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class FinalizedBarEvidence:
    symbol: str
    interval: str
    observed_at: datetime
    session_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    available_at: datetime
    finalized_at: datetime
    revision_id: str
    revision_status: str
    adjustment_basis: str
    source_reference: str

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume, self.amount)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("bar values must be finite and non-negative")
        if self.finalized_at < self.observed_at or self.available_at < self.observed_at:
            raise ValueError("bar availability/finality precedes observation")


@dataclass(frozen=True, slots=True)
class EvaluationMarkEvidence:
    decision_date: date
    next_session_date: date
    symbol: str
    evaluation_time: datetime
    evaluation_mark_id: str
    evaluation_price: float | None
    price_rule_id: str
    minute_path_complete_to_1030: bool
    available_at: datetime | None
    finalized_at: datetime | None
    missing_reason: str | None


@dataclass(frozen=True, slots=True)
class QualifiedPITMarketArtifact:
    schema_version: str
    source: XuntouPITSourceArtifact
    qualification_id: str
    provider_artifact_id: str
    authority: str

    def __post_init__(self) -> None:
        if self.schema_version != QUALIFIED_PIT_MARKET_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("qualified PIT market Artifact schema mismatch")
        if self.authority != "CONTROLLED_REPLICATION_INPUT":
            raise ValueError("qualified PIT input cannot gain production authority")
