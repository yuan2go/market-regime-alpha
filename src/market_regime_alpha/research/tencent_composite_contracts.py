"""Contracts for the Tencent/local/BaoStock exploratory research boundary.

These contracts preserve source identity and explicitly cap authority at EXPLORATORY.
They do not assert provider-backed PIT, availability, finality, or buyability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract, ProviderReference


TENCENT_COMPOSITE_SCHEMA_VERSION = "tencent-composite-exploratory-v1"
TENCENT_COMPOSITE_DECISION_CONVENTION = "tencent-composite-1455-one-full-5m-lag-v1"
CURRENT_WATCHLIST_BACKFILL_BIAS = "CURRENT_WATCHLIST_BACKFILL_BIAS"


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _require_unique(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class CompositeSourceKind(str, Enum):
    """Identified source owning one normalized composite row."""

    TENCENT = "TENCENT"
    LOCAL = "LOCAL"
    BAOSTOCK = "BAOSTOCK"


class CompositeDispositionCode(str, Enum):
    """Final per-symbol disposition emitted by the quality gate."""

    ACCEPTED = "ACCEPTED"
    REJECTED_INSUFFICIENT_WARMUP = "REJECTED_INSUFFICIENT_WARMUP"
    REJECTED_INSUFFICIENT_DECISION_DATES = "REJECTED_INSUFFICIENT_DECISION_DATES"
    REJECTED_HISTORY_GAP = "REJECTED_HISTORY_GAP"
    REJECTED_TIMESTAMP_SEMANTICS = "REJECTED_TIMESTAMP_SEMANTICS"
    REJECTED_INVALID_PRICE = "REJECTED_INVALID_PRICE"
    REJECTED_SOURCE_CONFLICT = "REJECTED_SOURCE_CONFLICT"
    REJECTED_FETCH_FAILURE = "REJECTED_FETCH_FAILURE"


@dataclass(frozen=True, slots=True)
class CompositeBar:
    """One validated normalized 5-minute row with explicit source identity."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: CompositeSourceKind

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        _require_aware("timestamp", self.timestamp)
        if not isinstance(self.source, CompositeSourceKind):
            raise TypeError("source must be a CompositeSourceKind")
        prices = (self.open, self.high, self.low, self.close)
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise ValueError("OHLC values must be finite and positive")
        if (
            self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
            or self.low > self.high
        ):
            raise ValueError("invalid OHLC relationship")
        if not math.isfinite(self.volume) or not math.isfinite(self.amount):
            raise ValueError("volume and amount must be finite")
        if self.volume < 0.0 or self.amount < 0.0:
            raise ValueError("volume and amount must be non-negative")


@dataclass(frozen=True, slots=True)
class CompositeSourcePartition:
    """Manifest for one exact normalized provider/symbol partition."""

    source: CompositeSourceKind
    provider_id: ProviderId
    product: str
    retrieved_at: RetrievedAt
    locator: str
    content_hash: str
    requested_symbols: tuple[str, ...]
    raw_row_count: int
    normalized_row_count: int
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, CompositeSourceKind):
            raise TypeError("source must be a CompositeSourceKind")
        for label, value in (
            ("product", self.product),
            ("locator", self.locator),
            ("content_hash", self.content_hash),
        ):
            _require_non_empty(label, value)
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("content_hash must use sha256: prefix")
        if not self.requested_symbols:
            raise ValueError("requested_symbols must not be empty")
        _require_unique("requested_symbols", self.requested_symbols)
        if self.raw_row_count < 0 or self.normalized_row_count < 0:
            raise ValueError("row counts must be non-negative")


@dataclass(frozen=True, slots=True)
class CompositeSourceAttempt:
    """One bounded fetch attempt retained for diagnostics."""

    provider: str
    symbol: str
    attempt_number: int
    success: bool
    message: str = ""

    def __post_init__(self) -> None:
        _require_non_empty("provider", self.provider)
        _require_non_empty("symbol", self.symbol)
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be positive")


@dataclass(frozen=True, slots=True)
class CompositeSourceConflict:
    """Non-identical rows sharing one symbol/timestamp key."""

    key: tuple[str, datetime]
    selected: CompositeBar
    rejected: CompositeBar

    def __post_init__(self) -> None:
        symbol, timestamp = self.key
        _require_non_empty("conflict symbol", symbol)
        _require_aware("conflict timestamp", timestamp)
        if (self.selected.symbol, self.selected.timestamp) != self.key:
            raise ValueError("selected row must match conflict key")
        if (self.rejected.symbol, self.rejected.timestamp) != self.key:
            raise ValueError("rejected row must match conflict key")
        if self.selected.source is self.rejected.source:
            raise ValueError("source conflict requires different sources")


@dataclass(frozen=True, slots=True)
class CompositeMergeResult:
    """Deterministically selected bars plus retained conflicts."""

    bars: tuple[CompositeBar, ...]
    conflicts: tuple[CompositeSourceConflict, ...]

    def __post_init__(self) -> None:
        keys = tuple((bar.symbol, bar.timestamp) for bar in self.bars)
        _require_unique("merged bar keys", keys)
        if tuple(sorted(self.bars, key=lambda bar: (bar.timestamp, bar.symbol))) != self.bars:
            raise ValueError("merged bars must be sorted by timestamp and symbol")


@dataclass(frozen=True, slots=True)
class CompositeQualityFinding:
    """One stable machine-readable quality observation."""

    code: str
    message: str
    critical: bool

    def __post_init__(self) -> None:
        _require_non_empty("finding code", self.code)
        _require_non_empty("finding message", self.message)


@dataclass(frozen=True, slots=True)
class CompositeSymbolDisposition:
    """Quality-gate result for one requested symbol."""

    symbol: str
    code: CompositeDispositionCode
    complete_session_count: int
    findings: tuple[CompositeQualityFinding, ...]

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        if not isinstance(self.code, CompositeDispositionCode):
            raise TypeError("code must be a CompositeDispositionCode")
        if self.complete_session_count < 0:
            raise ValueError("complete_session_count must be non-negative")


@dataclass(frozen=True, slots=True)
class CompositeQualityReport:
    """Complete 20-symbol quality decision and cross-sectional coverage."""

    requested_symbols: tuple[str, ...]
    accepted_symbols: tuple[str, ...]
    dispositions: tuple[CompositeSymbolDisposition, ...]
    common_session_dates: tuple[date, ...]
    required_session_count: int
    minimum_accepted_symbols: int

    def __post_init__(self) -> None:
        if not self.requested_symbols:
            raise ValueError("requested_symbols must not be empty")
        _require_unique("requested_symbols", self.requested_symbols)
        _require_unique("accepted_symbols", self.accepted_symbols)
        _require_unique("common_session_dates", self.common_session_dates)
        if tuple(sorted(self.common_session_dates)) != self.common_session_dates:
            raise ValueError("common_session_dates must be sorted")
        if self.required_session_count <= 0 or self.minimum_accepted_symbols <= 0:
            raise ValueError("quality thresholds must be positive")
        disposition_symbols = tuple(item.symbol for item in self.dispositions)
        if set(disposition_symbols) != set(self.requested_symbols) or len(disposition_symbols) != len(
            self.requested_symbols
        ):
            raise ValueError("dispositions must cover every requested symbol exactly once")
        accepted_from_dispositions = {
            item.symbol for item in self.dispositions if item.code is CompositeDispositionCode.ACCEPTED
        }
        if accepted_from_dispositions != set(self.accepted_symbols):
            raise ValueError("accepted_symbols must match ACCEPTED dispositions")

    @property
    def success(self) -> bool:
        return (
            len(self.accepted_symbols) >= self.minimum_accepted_symbols
            and len(self.common_session_dates) >= self.required_session_count
        )


@dataclass(frozen=True, slots=True)
class PreparedCompositeSession:
    """One complete exploratory session used by Feature/Target materialization."""

    symbol: str
    session_date: date
    open: float
    high: float
    low: float
    close: float
    amount: float
    reference_price: float
    reference_timestamp: datetime
    source_kinds: tuple[CompositeSourceKind, ...]

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        _require_aware("reference_timestamp", self.reference_timestamp)
        if self.reference_timestamp.date() != self.session_date:
            raise ValueError("reference_timestamp must fall on session_date")
        prices = (self.open, self.high, self.low, self.close, self.reference_price)
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise ValueError("session prices must be finite and positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid session OHLC relationship")
        if not math.isfinite(self.amount) or self.amount < 0.0:
            raise ValueError("session amount must be finite and non-negative")
        if not self.source_kinds:
            raise ValueError("source_kinds must not be empty")
        _require_unique("source_kinds", self.source_kinds)


@dataclass(frozen=True, slots=True)
class PreparedCompositeData:
    """Accepted symbols and aligned complete sessions for one exploratory run."""

    accepted_symbols: tuple[str, ...]
    common_session_dates: tuple[date, ...]
    sessions: tuple[PreparedCompositeSession, ...]
    quality: CompositeQualityReport
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.accepted_symbols:
            raise ValueError("accepted_symbols must not be empty")
        _require_unique("accepted_symbols", self.accepted_symbols)
        _require_unique("common_session_dates", self.common_session_dates)
        keys = tuple((session.symbol, session.session_date) for session in self.sessions)
        _require_unique("prepared session keys", keys)
        if tuple(sorted(self.common_session_dates)) != self.common_session_dates:
            raise ValueError("common_session_dates must be sorted")
        if self.accepted_symbols != self.quality.accepted_symbols:
            raise ValueError("accepted_symbols must match quality report")

    def session_for(self, symbol: str, session_date: date) -> PreparedCompositeSession:
        for session in self.sessions:
            if session.symbol == symbol and session.session_date == session_date:
                return session
        raise KeyError(f"prepared session unavailable: {symbol} {session_date.isoformat()}")

    def next_session_date(self, session_date: date) -> date:
        try:
            index = self.common_session_dates.index(session_date)
        except ValueError as exc:
            raise KeyError(f"session date unavailable: {session_date.isoformat()}") from exc
        if index + 1 >= len(self.common_session_dates):
            raise KeyError(f"following session unavailable: {session_date.isoformat()}")
        return self.common_session_dates[index + 1]


@dataclass(frozen=True, slots=True)
class CompositeAcquisitionResult:
    """All identified source partitions and Tencent quotes from one acquisition."""

    partitions: tuple[CompositeSourcePartition, ...]
    quote_partition: CompositeSourcePartition
    attempts: tuple[CompositeSourceAttempt, ...]
    bars: tuple[CompositeBar, ...]
    quotes: Mapping[str, Any]
    retrieved_at: RetrievedAt

    def __post_init__(self) -> None:
        if not self.partitions:
            raise ValueError("partitions must not be empty")
        bar_keys = tuple((bar.source, bar.symbol, bar.timestamp) for bar in self.bars)
        _require_unique("acquired source bar keys", bar_keys)
        object.__setattr__(self, "quotes", MappingProxyType(dict(self.quotes)))


def build_tencent_composite_dataset_contract(
    *,
    watchlist_hash: str,
    source_content_hashes: tuple[str, ...],
    code_revision: str,
    config_hash: str,
) -> DatasetContract:
    """Build a content-derived Dataset identity capped at EXPLORATORY."""

    for label, value in (
        ("watchlist_hash", watchlist_hash),
        ("code_revision", code_revision),
        ("config_hash", config_hash),
    ):
        _require_non_empty(label, value)
    if not source_content_hashes:
        raise ValueError("source_content_hashes must not be empty")
    if any(not value.startswith("sha256:") for value in source_content_hashes):
        raise ValueError("source content hashes must use sha256: prefix")
    payload = {
        "schema_version": TENCENT_COMPOSITE_SCHEMA_VERSION,
        "watchlist_hash": watchlist_hash,
        "source_content_hashes": sorted(source_content_hashes),
        "code_revision": code_revision,
        "config_hash": config_hash,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return DatasetContract(
        dataset_id=DatasetId(f"tencent-composite-exploratory-{digest[:24]}"),
        schema_version=TENCENT_COMPOSITE_SCHEMA_VERSION,
        eligibility=DataEligibility.EXPLORATORY,
        manifest_artifact_id=ArtifactId(f"tencent-composite-manifest-{digest[:24]}"),
        provider_references=(
            ProviderReference(
                ProviderId("provider-tencent-public"),
                "minute-and-quote",
                "observed-v1",
            ),
            ProviderReference(
                ProviderId("provider-local-cache"),
                "dividend-t-5min-cache",
                "v1",
            ),
            ProviderReference(
                ProviderId("provider-baostock"),
                "historical-5min-backfill",
                "v1",
            ),
        ),
        pit_correct_for_scope=False,
        scope="20-symbol Tencent/local/BaoStock exploratory Candidate run",
        limitations=(
            CURRENT_WATCHLIST_BACKFILL_BIAS,
            "HISTORICAL_AVAILABILITY_UNVERIFIED",
            "FIVE_MINUTE_BAR_LABEL_SEMANTICS_UNVERIFIED",
            "PRICE_ADJUSTMENT_REVISION_HISTORY_UNVERIFIED",
        ),
    )
