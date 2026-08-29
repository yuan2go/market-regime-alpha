"""Provider, instrument, and classification reference facts."""

from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID

from market_regime_alpha.market.domain.vocabulary import (
    BarTimeframe,
    ClassificationEvidenceStatus,
    InstrumentFactKind,
    InstrumentType,
    MarketFactKind,
    MembershipStatus,
    PriceBasis,
    ProviderKind,
    SourceAvailabilityStatus,
)
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import require_utc

_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


@dataclass(frozen=True, slots=True)
class Provider:
    provider_id: UUID
    provider_code: str
    display_name: str
    provider_kind: ProviderKind

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", self.provider_code):
            raise ValueError("provider_code has an invalid format")
        if not self.display_name:
            raise ValueError("display_name is required")
        if not isinstance(self.provider_kind, ProviderKind):
            raise TypeError("provider_kind must be ProviderKind")


@dataclass(frozen=True, slots=True)
class ProviderProduct:
    provider_product_id: UUID
    provider_id: UUID
    product_code: str
    revision: int
    payload_family: str
    media_type: str
    payload_encoding: str
    source_availability_policy: SourceAvailabilityStatus
    fact_kinds: tuple[MarketFactKind, ...]
    instrument_fact_kinds: tuple[InstrumentFactKind, ...]
    bar_timeframes: tuple[BarTimeframe, ...]
    price_bases: tuple[PriceBasis, ...]
    supersedes_provider_product_id: UUID | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", self.product_code):
            raise ValueError("product_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_provider_product_id is None):
            raise ValueError("product revision chain is incomplete")
        if not _CODE.fullmatch(self.payload_family):
            raise ValueError("payload_family has an invalid format")
        if not self.media_type or not self.payload_encoding:
            raise ValueError("payload media type and encoding are required")
        if not isinstance(
            self.source_availability_policy,
            SourceAvailabilityStatus,
        ):
            raise TypeError("source_availability_policy must be SourceAvailabilityStatus")
        if not self.fact_kinds or any(not isinstance(item, MarketFactKind) for item in self.fact_kinds):
            raise TypeError("fact_kinds must contain typed MarketFactKind values")
        if len(set(self.fact_kinds)) != len(self.fact_kinds):
            raise ValueError("fact_kinds cannot contain duplicates")
        if any(not isinstance(item, InstrumentFactKind) for item in self.instrument_fact_kinds):
            raise TypeError("instrument_fact_kinds must contain typed InstrumentFactKind values")
        if len(set(self.instrument_fact_kinds)) != len(self.instrument_fact_kinds):
            raise ValueError("instrument_fact_kinds cannot contain duplicates")
        if any(not isinstance(item, BarTimeframe) for item in self.bar_timeframes):
            raise TypeError("bar_timeframes must contain typed BarTimeframe values")
        if len(set(self.bar_timeframes)) != len(self.bar_timeframes):
            raise ValueError("bar_timeframes cannot contain duplicates")
        if any(not isinstance(item, PriceBasis) for item in self.price_bases):
            raise TypeError("price_bases must contain typed PriceBasis values")
        if len(set(self.price_bases)) != len(self.price_bases):
            raise ValueError("price_bases cannot contain duplicates")
        carries_bars = MarketFactKind.MARKET_BAR in self.fact_kinds
        if carries_bars != bool(self.bar_timeframes) or carries_bars != bool(self.price_bases):
            raise ValueError("MARKET_BAR products require explicit timeframe and price-basis capabilities")
        carries_instrument_facts = MarketFactKind.INSTRUMENT_FACT in self.fact_kinds
        if carries_instrument_facts != bool(self.instrument_fact_kinds):
            raise ValueError("INSTRUMENT_FACT products require explicit fact-kind capabilities")


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: InstrumentId
    canonical_code: str
    exchange: str
    instrument_type: InstrumentType
    currency: str
    source_capture_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", self.canonical_code):
            raise ValueError("canonical_code has an invalid format")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,15}", self.exchange):
            raise ValueError("exchange has an invalid format")
        if not isinstance(self.instrument_type, InstrumentType):
            raise TypeError("instrument_type must be InstrumentType")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency must be an ISO-style three-letter code")


@dataclass(frozen=True, slots=True)
class InstrumentIdentifier:
    instrument_identifier_id: UUID
    instrument_id: InstrumentId
    identifier_scheme: str
    identifier_value: str
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_identifier_id: UUID | None
    source_capture_id: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", self.identifier_scheme):
            raise ValueError("identifier_scheme has an invalid format")
        if not self.identifier_value:
            raise ValueError("identifier_value is required")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("identifier effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_identifier_id is None):
            raise ValueError("identifier revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationRevision:
    classification_id: UUID
    classification_scheme: str
    classification_code: str
    display_name: str
    revision: int
    effective_from: datetime
    effective_to: datetime | None
    supersedes_classification_id: UUID | None
    source_capture_id: UUID

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", self.classification_scheme):
            raise ValueError("classification_scheme has an invalid format")
        if not self.classification_code or not self.display_name:
            raise ValueError("classification code and name are required")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("classification effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_classification_id is None):
            raise ValueError("classification revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationMembershipRevision:
    membership_revision_id: UUID
    classification_id: UUID
    instrument_id: InstrumentId
    source_capture_id: UUID
    membership_status: MembershipStatus
    effective_from: datetime
    effective_to: datetime | None
    revision: int
    supersedes_membership_revision_id: UUID | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", InstrumentId.parse(self.instrument_id))
        if not isinstance(self.membership_status, MembershipStatus):
            raise TypeError("membership_status must be MembershipStatus")
        object.__setattr__(self, "effective_from", require_utc(self.effective_from, field="effective_from"))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", require_utc(self.effective_to, field="effective_to"))
            if self.effective_to <= self.effective_from:
                raise ValueError("membership effective interval must be positive")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_membership_revision_id is None):
            raise ValueError("membership revision chain is incomplete")


@dataclass(frozen=True, slots=True)
class ClassificationMembersResult:
    """Distinguish verified empty membership from absent Classification evidence."""

    status: ClassificationEvidenceStatus
    members: tuple[InstrumentId, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ClassificationEvidenceStatus):
            raise TypeError("status must be ClassificationEvidenceStatus")
        object.__setattr__(
            self,
            "members",
            tuple(InstrumentId.parse(item) for item in self.members),
        )
        if self.status is ClassificationEvidenceStatus.MISSING and self.members:
            raise ValueError("missing Classification evidence cannot contain members")
