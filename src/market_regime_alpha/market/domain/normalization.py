"""Typed gaps and one-capture normalization batches."""

from dataclasses import dataclass
from datetime import date, datetime
import re
from uuid import UUID

from market_regime_alpha.market.domain.facts import (
    CorporateActionRevision,
    InstrumentFactRevision,
    InstrumentLifecycleFactRevision,
    MarketBarRevision,
    SecurityStatusFactRevision,
)
from market_regime_alpha.market.domain.reference import (
    ClassificationMembershipRevision,
    ClassificationRevision,
    Instrument,
    InstrumentIdentifier,
)
from market_regime_alpha.market.domain.temporal import TradingSession
from market_regime_alpha.market.domain.vocabulary import (
    BarTimeframe,
    EvidenceScope,
    GapFactKind,
    GapKind,
    GapReasonCode,
    InstrumentFactKind,
    MarketFactKind,
    PriceBasis,
)
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class SourceGap:
    gap_id: UUID
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: InstrumentId | None
    session_id: TradingSessionId | None
    gap_kind: GapKind
    reason_code: GapReasonCode
    fact_kind: GapFactKind
    instrument_fact_kind: InstrumentFactKind | None
    timeframe: BarTimeframe | None
    price_basis: PriceBasis | None
    event_start: datetime | None
    event_end: datetime | None
    detail: str | None
    evidence_scope: EvidenceScope | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    instrument_code: str | None = None
    identifier_scheme: str | None = None
    identifier_value: str | None = None
    exchange: str | None = None
    session_date: date | None = None
    classification_scheme: str | None = None
    classification_code: str | None = None
    action_key: str | None = None

    def __post_init__(self) -> None:
        if self.instrument_id is not None:
            object.__setattr__(
                self,
                "instrument_id",
                InstrumentId.parse(self.instrument_id),
            )
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                TradingSessionId.parse(self.session_id),
            )
        if not isinstance(self.gap_kind, GapKind):
            raise TypeError("gap_kind must be GapKind")
        if not isinstance(self.reason_code, GapReasonCode):
            raise TypeError("reason_code must be GapReasonCode")
        allowed_reasons = {
            GapKind.MISSING: {
                GapReasonCode.NO_ROWS_RETURNED,
                GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                GapReasonCode.EXACT_BAR_MISSING,
            },
            GapKind.PLACEHOLDER: {GapReasonCode.NULL_OHLC_PLACEHOLDER},
            GapKind.PROVIDER_FAILURE: {GapReasonCode.PROVIDER_FAILURE},
            GapKind.CONFLICT: {GapReasonCode.CONFLICTING_SOURCE_REVISIONS},
            GapKind.INVALID_OHLC: {GapReasonCode.INVALID_OHLC},
        }[self.gap_kind]
        if self.reason_code not in allowed_reasons:
            raise ValueError("reason_code is incompatible with gap_kind")
        if not isinstance(self.fact_kind, GapFactKind):
            raise TypeError("fact_kind must be GapFactKind")
        if self.instrument_fact_kind is not None and not isinstance(
            self.instrument_fact_kind,
            InstrumentFactKind,
        ):
            raise TypeError("instrument_fact_kind must be InstrumentFactKind when present")
        if (self.fact_kind is GapFactKind.INSTRUMENT_FACT) != (self.instrument_fact_kind is not None):
            raise ValueError("instrument-fact gaps require one exact instrument_fact_kind")
        if self.timeframe is not None and not isinstance(self.timeframe, BarTimeframe):
            raise TypeError("timeframe must be BarTimeframe when present")
        if self.price_basis is not None and not isinstance(
            self.price_basis,
            PriceBasis,
        ):
            raise TypeError("price_basis must be PriceBasis when present")
        if self.event_start is None and self.event_end is not None:
            raise ValueError("gap event_end requires event_start")
        if self.event_start is not None:
            object.__setattr__(
                self,
                "event_start",
                require_utc(self.event_start, field="event_start"),
            )
        if self.event_end is not None:
            object.__setattr__(
                self,
                "event_end",
                require_utc(self.event_end, field="event_end"),
            )
        if self.event_start is not None and self.event_end is not None:
            if self.event_end <= self.event_start:
                raise ValueError("gap event interval must be positive")
        if self.effective_from is None and self.effective_to is not None:
            raise ValueError("gap effective_to requires effective_from")
        if self.effective_from is not None:
            object.__setattr__(
                self,
                "effective_from",
                require_utc(self.effective_from, field="effective_from"),
            )
        if self.effective_to is not None:
            object.__setattr__(
                self,
                "effective_to",
                require_utc(self.effective_to, field="effective_to"),
            )
        if self.effective_from is not None and self.effective_to is not None:
            if self.effective_to <= self.effective_from:
                raise ValueError("gap effective interval must be positive")
        if self.evidence_scope is not None and not isinstance(
            self.evidence_scope,
            EvidenceScope,
        ):
            raise TypeError("evidence_scope must be EvidenceScope when present")
        if (self.timeframe is None) != (self.price_basis is None):
            raise ValueError("bar gaps require both timeframe and price basis")
        if (self.fact_kind is GapFactKind.MARKET_BAR) != (self.timeframe is not None):
            raise ValueError("only MARKET_BAR gaps carry timeframe and price basis")
        if self.fact_kind is GapFactKind.MARKET_BAR and (
            self.instrument_id is None or self.session_id is None or self.event_start is None or self.event_end is None
        ):
            raise ValueError("MARKET_BAR gaps require exact Instrument, Session, and event interval")
        if (
            self.reason_code
            in {
                GapReasonCode.EXACT_BAR_MISSING,
                GapReasonCode.NULL_OHLC_PLACEHOLDER,
                GapReasonCode.INVALID_OHLC,
            }
            and self.fact_kind is not GapFactKind.MARKET_BAR
        ):
            raise ValueError("OHLC and exact-bar reasons require a MARKET_BAR gap")
        for field_name, pattern in (
            ("instrument_code", r"[A-Z0-9][A-Z0-9._-]{0,31}"),
            ("identifier_scheme", r"[A-Z][A-Z0-9_]{0,31}"),
            ("exchange", r"[A-Z][A-Z0-9]{1,15}"),
            ("classification_scheme", r"[A-Z][A-Z0-9_]{0,31}"),
        ):
            value = getattr(self, field_name)
            if value is not None and not re.fullmatch(pattern, value):
                raise ValueError(f"{field_name} has an invalid format")
        for field_name in (
            "identifier_value",
            "classification_code",
            "action_key",
        ):
            value = getattr(self, field_name)
            if value is not None and not value:
                raise ValueError(f"{field_name} cannot be empty")
        session_fact_kinds = {
            InstrumentFactKind.SECURITY_STATUS,
            InstrumentFactKind.LIMIT_UP_PRICE,
            InstrumentFactKind.LIMIT_DOWN_PRICE,
            InstrumentFactKind.REFERENCE_PRICE,
        }
        effective_fact_kinds = {
            InstrumentFactKind.LISTING_STATUS,
            InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
            InstrumentFactKind.TOTAL_SHARES,
            InstrumentFactKind.FREE_FLOAT_SHARES,
        }
        exact_scope = {
            GapFactKind.DATA_CAPTURE: not any(
                (
                    self.instrument_id,
                    self.session_id,
                    self.evidence_scope,
                    self.instrument_code,
                    self.identifier_scheme,
                    self.identifier_value,
                    self.exchange,
                    self.session_date,
                    self.classification_scheme,
                    self.classification_code,
                    self.action_key,
                    self.event_start,
                    self.effective_from,
                )
            ),
            GapFactKind.INSTRUMENT: (
                self.instrument_code is not None
                and self.instrument_id is None
                and self.session_id is None
                and self.evidence_scope is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.INSTRUMENT_IDENTIFIER: (
                self.identifier_scheme is not None
                and self.identifier_value is not None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.TRADING_SESSION: (
                self.exchange is not None
                and self.session_date is not None
                and self.session_id is None
                and self.instrument_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.CLASSIFICATION: (
                self.classification_scheme is not None
                and self.classification_code is not None
                and self.instrument_id is None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.CLASSIFICATION_MEMBERSHIP: (
                self.classification_scheme is not None
                and self.classification_code is not None
                and self.instrument_id is not None
                and self.session_id is None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.action_key is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is not None
            ),
            GapFactKind.MARKET_BAR: (
                self.instrument_id is not None
                and self.session_id is not None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and self.event_start is not None
                and self.event_end is not None
                and self.effective_from is None
                and self.effective_to is None
            ),
            GapFactKind.INSTRUMENT_FACT: (
                self.instrument_id is not None
                and self.instrument_fact_kind is not None
                and self.evidence_scope is not None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.action_key is None
                and (
                    (
                        self.instrument_fact_kind in session_fact_kinds
                        and self.session_id is not None
                        and self.evidence_scope
                        in {
                            EvidenceScope.DECISION_SESSION,
                            EvidenceScope.PRIOR_SESSION,
                        }
                        and self.event_start is not None
                        and self.event_end is not None
                        and self.effective_from is None
                        and self.effective_to is None
                    )
                    or (
                        self.instrument_fact_kind in effective_fact_kinds
                        and self.session_id is None
                        and self.evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL
                        and self.event_start is None
                        and self.event_end is None
                        and self.effective_from is not None
                    )
                )
            ),
            GapFactKind.CORPORATE_ACTION: (
                self.instrument_id is not None
                and self.session_id is not None
                and self.action_key is not None
                and self.evidence_scope is None
                and self.instrument_code is None
                and self.identifier_scheme is None
                and self.identifier_value is None
                and self.exchange is None
                and self.session_date is None
                and self.classification_scheme is None
                and self.classification_code is None
                and self.event_start is None
                and self.event_end is None
                and self.effective_from is None
                and self.effective_to is None
            ),
        }[self.fact_kind]
        if not exact_scope:
            raise ValueError(f"{self.fact_kind.value} gap requires its exact typed scope")

    @property
    def disposition_key(self) -> tuple[object, ...]:
        """One Capture has one disposition for one exact expected fact."""

        return (
            self.capture_id,
            self.fact_kind,
            self.instrument_id,
            self.session_id,
            self.instrument_fact_kind,
            self.evidence_scope,
            self.timeframe,
            self.price_basis,
            self.event_start,
            self.event_end,
            self.effective_from,
            self.effective_to,
            self.instrument_code,
            self.identifier_scheme,
            self.identifier_value,
            self.exchange,
            self.session_date,
            self.classification_scheme,
            self.classification_code,
            self.action_key,
        )


class MarketEvidenceGapError(RuntimeError):
    """The current PIT disposition is a typed gap, not an older fact."""

    def __init__(self, gap: SourceGap) -> None:
        self.gap = gap
        super().__init__(f"{gap.fact_kind.value} evidence is {gap.gap_kind.value}: {gap.reason_code.value}")


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    source_capture_id: UUID
    source_provider_product_id: UUID
    instruments: tuple[Instrument, ...] = ()
    instrument_identifiers: tuple[InstrumentIdentifier, ...] = ()
    trading_sessions: tuple[TradingSession, ...] = ()
    classifications: tuple[ClassificationRevision, ...] = ()
    classification_memberships: tuple[ClassificationMembershipRevision, ...] = ()
    bars: tuple[MarketBarRevision, ...] = ()
    instrument_facts: tuple[InstrumentFactRevision, ...] = ()
    security_status_facts: tuple[SecurityStatusFactRevision, ...] = ()
    lifecycle_status_facts: tuple[InstrumentLifecycleFactRevision, ...] = ()
    corporate_actions: tuple[CorporateActionRevision, ...] = ()
    gaps: tuple[SourceGap, ...] = ()

    def __post_init__(self) -> None:
        evidence = (
            *self.instruments,
            *self.instrument_identifiers,
            *self.trading_sessions,
            *self.classifications,
            *self.classification_memberships,
            *self.bars,
            *self.instrument_facts,
            *self.security_status_facts,
            *self.lifecycle_status_facts,
            *self.corporate_actions,
            *self.gaps,
        )
        if not evidence:
            raise ValueError("normalization must record a fact revision or typed SourceGap")
        if any(_evidence_capture_id(item) != self.source_capture_id for item in evidence):
            raise ValueError("normalization output must bind one exact Capture")
        products = tuple(item.provider_product_id for item in evidence if hasattr(item, "provider_product_id"))
        if any(item != self.source_provider_product_id for item in products):
            raise ValueError("normalization output must bind the Capture's ProviderProduct")
        gap_keys = tuple(item.disposition_key for item in self.gaps)
        if len(gap_keys) != len(set(gap_keys)):
            raise ValueError("one Capture must have one SourceGap disposition per expected fact")
        if any(_gap_conflicts_with_batch_fact(self, gap) for gap in self.gaps):
            raise ValueError("one Capture cannot assert both a canonical fact and a SourceGap for the same expected observation")

    @property
    def required_fact_kinds(self) -> frozenset[MarketFactKind]:
        required: set[MarketFactKind] = set()
        for values, kind in (
            (self.instruments, MarketFactKind.INSTRUMENT),
            (self.instrument_identifiers, MarketFactKind.INSTRUMENT_IDENTIFIER),
            (self.trading_sessions, MarketFactKind.TRADING_SESSION),
            (self.classifications, MarketFactKind.CLASSIFICATION),
            (
                self.classification_memberships,
                MarketFactKind.CLASSIFICATION_MEMBERSHIP,
            ),
            (self.bars, MarketFactKind.MARKET_BAR),
            (
                (
                    *self.instrument_facts,
                    *self.security_status_facts,
                    *self.lifecycle_status_facts,
                ),
                MarketFactKind.INSTRUMENT_FACT,
            ),
            (self.corporate_actions, MarketFactKind.CORPORATE_ACTION),
        ):
            if values:
                required.add(kind)
        for gap in self.gaps:
            try:
                required.add(MarketFactKind(gap.fact_kind.value))
            except ValueError:
                # Capture-level gaps do not invent a Market fact.
                pass
        return frozenset(required)

    @property
    def required_instrument_fact_kinds(self) -> frozenset[InstrumentFactKind]:
        required = {InstrumentFactKind(item.fact_kind.value) for item in self.instrument_facts}
        if self.security_status_facts:
            required.add(InstrumentFactKind.SECURITY_STATUS)
        required.update(item.fact_kind for item in self.lifecycle_status_facts)
        required.update(item.instrument_fact_kind for item in self.gaps if item.instrument_fact_kind is not None)
        return frozenset(required)


def _gap_conflicts_with_batch_fact(
    batch: NormalizationBatch,
    gap: SourceGap,
) -> bool:
    if gap.fact_kind is GapFactKind.DATA_CAPTURE:
        return False
    if gap.fact_kind is GapFactKind.INSTRUMENT:
        return any(item.canonical_code == gap.instrument_code for item in batch.instruments)
    if gap.fact_kind is GapFactKind.INSTRUMENT_IDENTIFIER:
        return any(
            item.identifier_scheme == gap.identifier_scheme
            and item.identifier_value == gap.identifier_value
            and (gap.instrument_id is None or item.instrument_id == gap.instrument_id)
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            for item in batch.instrument_identifiers
        )
    if gap.fact_kind is GapFactKind.TRADING_SESSION:
        return any(item.exchange == gap.exchange and item.session_date == gap.session_date for item in batch.trading_sessions)
    if gap.fact_kind is GapFactKind.CLASSIFICATION:
        return any(
            item.classification_scheme == gap.classification_scheme
            and item.classification_code == gap.classification_code
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            for item in batch.classifications
        )
    if gap.fact_kind is GapFactKind.CLASSIFICATION_MEMBERSHIP:
        classification_by_id = {item.classification_id: item for item in batch.classifications}
        return any(
            item.instrument_id == gap.instrument_id
            and item.effective_from == gap.effective_from
            and item.effective_to == gap.effective_to
            and (classification := classification_by_id.get(item.classification_id)) is not None
            and classification.classification_scheme == gap.classification_scheme
            and classification.classification_code == gap.classification_code
            for item in batch.classification_memberships
        )
    if gap.fact_kind is GapFactKind.MARKET_BAR:
        return any(
            item.instrument_id == gap.instrument_id
            and item.session_id == gap.session_id
            and item.timeframe == gap.timeframe
            and item.price_basis == gap.price_basis
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.bars
        )
    if gap.fact_kind is GapFactKind.CORPORATE_ACTION:
        return any(
            item.instrument_id == gap.instrument_id and item.ex_session_id == gap.session_id and item.action_key == gap.action_key
            for item in batch.corporate_actions
        )
    if gap.instrument_fact_kind is None:
        raise AssertionError("INSTRUMENT_FACT SourceGap lost its typed fact kind")
    if gap.evidence_scope is not EvidenceScope.EFFECTIVE_INTERVAL:
        numeric_conflict = any(
            item.instrument_id == gap.instrument_id
            and item.fact_kind.value == gap.instrument_fact_kind.value
            and item.session_id == gap.session_id
            and item.evidence_scope == gap.evidence_scope
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.instrument_facts
        )
        security_conflict = any(
            gap.instrument_fact_kind is InstrumentFactKind.SECURITY_STATUS
            and item.instrument_id == gap.instrument_id
            and item.session_id == gap.session_id
            and item.evidence_scope == gap.evidence_scope
            and item.event_start == gap.event_start
            and item.event_end == gap.event_end
            for item in batch.security_status_facts
        )
        return numeric_conflict or security_conflict
    numeric_conflict = any(
        item.instrument_id == gap.instrument_id
        and item.fact_kind.value == gap.instrument_fact_kind.value
        and item.evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL
        and item.event_start == gap.effective_from
        and item.event_end == gap.effective_to
        for item in batch.instrument_facts
    )
    lifecycle_conflict = any(
        item.instrument_id == gap.instrument_id
        and item.fact_kind == gap.instrument_fact_kind
        and item.effective_from == gap.effective_from
        and item.effective_to == gap.effective_to
        for item in batch.lifecycle_status_facts
    )
    return numeric_conflict or lifecycle_conflict


def _evidence_capture_id(item: object) -> UUID:
    for field_name in ("capture_id", "source_capture_id"):
        value = getattr(item, field_name, None)
        if isinstance(value, UUID):
            return value
    raise TypeError("normalization evidence has no Capture identity")
