from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.market.domain import (
    BarTimeframe,
    CaptureStatus,
    EvidenceScope,
    GapFactKind,
    GapKind,
    GapReasonCode,
    MarketBarRevision,
    NormalizationBatch,
    ProviderCapture,
    PriceBasis,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SourceGap,
    TemporalEnvelope,
    TradingSession,
)
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit


UTC = timezone.utc


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 28, hour, minute, tzinfo=UTC)


def _cny(value: str) -> Money:
    return Money(Decimal(value), "CNY")


def _shares(value: str) -> Quantity:
    return Quantity(Decimal(value), QuantityUnit.SHARES)


def _temporal() -> TemporalEnvelope:
    return TemporalEnvelope(
        provider_time=_at(6, 55),
        source_availability_status=SourceAvailabilityStatus.UNKNOWN,
        source_available_at=None,
        capture_started_at=_at(6, 56),
        capture_completed_at=_at(6, 56) + timedelta(seconds=1),
        known_at=_at(6, 56) + timedelta(seconds=1),
        decision_visible_at=_at(6, 56) + timedelta(seconds=1),
    )


def _session() -> TradingSession:
    return TradingSession(
        session_id=uuid4(),
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        timezone_name="Asia/Shanghai",
        open_at=_at(1, 30),
        break_start_at=_at(3, 30),
        break_end_at=_at(5),
        close_at=_at(7),
        decision_reference_at=_at(6, 55),
        source_capture_id=uuid4(),
    )


def test_a_share_trading_session_timezone_is_frozen_to_asia_shanghai() -> None:
    with pytest.raises(ValueError, match="must be Asia/Shanghai"):
        replace(_session(), timezone_name="America/New_York")


def _bar(session: TradingSession, *, basis: PriceBasis = PriceBasis.RAW_UNADJUSTED) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=uuid4(),
        provider_product_id=uuid4(),
        capture_id=uuid4(),
        instrument_id=uuid4(),
        session_id=session.session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=basis,
        event_start=session.decision_reference_at - timedelta(minutes=5),
        event_end=session.decision_reference_at,
        revision=1,
        supersedes_revision_id=None,
        open=_cny("10.10"),
        high=_cny("10.30"),
        low=_cny("10.00"),
        close=_cny("10.20"),
        volume=_shares("0"),
        turnover=_cny("0"),
    )


def test_temporal_axes_remain_distinct_and_unqualified_visibility_is_known_time() -> None:
    temporal = _temporal()
    assert temporal.source_available_at is None
    assert temporal.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert temporal.decision_visible_at.value == temporal.known_at.value
    assert temporal.provider_time != temporal.capture_started_at

    with pytest.raises(ValueError, match="UNKNOWN source availability"):
        TemporalEnvelope(
            provider_time=_at(6, 55),
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=_at(6, 54),
            capture_started_at=_at(6, 56),
            capture_completed_at=_at(6, 57),
            known_at=_at(6, 57),
            decision_visible_at=_at(6, 57),
        )

    with pytest.raises(ValueError, match="decision_visible_at must equal known_at"):
        TemporalEnvelope(
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            capture_started_at=_at(6, 56),
            capture_completed_at=_at(6, 57),
            known_at=_at(6, 57),
            decision_visible_at=_at(6, 58),
        )

    with pytest.raises(ValueError, match="source_available_at cannot follow known_at"):
        TemporalEnvelope(
            provider_time=_at(6, 55),
            source_availability_status=SourceAvailabilityStatus.PROVIDER_REPORTED,
            source_available_at=_at(6, 58),
            capture_started_at=_at(6, 56),
            capture_completed_at=_at(6, 57),
            known_at=_at(6, 57),
            decision_visible_at=_at(6, 57),
        )


def test_capture_key_is_rejected_before_provider_or_artifact_io() -> None:
    with pytest.raises(ValueError, match="capture_key has an invalid format"):
        CaptureRequest(
            provider_product_id=uuid4(),
            capture_key="bad key",
            resource="https://example.invalid/market",
            request_headers_hash="0" * 64,
        )

    with pytest.raises(ValueError, match="capture_key has an invalid format"):
        replace(
            ProviderCapture(
                capture_id=uuid4(),
                provider_product_id=uuid4(),
                capture_key="valid-key",
                request_hash="0" * 64,
                status=CaptureStatus.CAPTURED,
                temporal=_temporal(),
                artifact_id=uuid4(),
                error_code=None,
                limitation_code=None,
                payload_encoding="utf-8",
            ),
            capture_key="bad key",
        )


def test_financial_values_are_typed_bounded_and_invalid_ohlc_never_becomes_a_bar() -> None:
    session = _session()
    assert _bar(session).volume == _shares("0")

    with pytest.raises(TypeError, match="OHLC values must be Money"):
        replace(_bar(session), open=10.1)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r"numeric\(30, 10\) scale"):
        _cny("10.12345678901")

    with pytest.raises(ValueError, match="legal OHLC"):
        MarketBarRevision(
            bar_revision_id=uuid4(),
            provider_product_id=uuid4(),
            capture_id=uuid4(),
            instrument_id=uuid4(),
            session_id=session.session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=session.decision_reference_at - timedelta(minutes=5),
            event_end=session.decision_reference_at,
            revision=1,
            supersedes_revision_id=None,
            open=_cny("10"),
            high=_cny("9"),
            low=_cny("8"),
            close=_cny("10"),
            volume=_shares("1"),
            turnover=None,
        )


def test_price_bases_are_distinct_logical_series() -> None:
    session = _session()
    raw = _bar(session)
    forward = _bar(session, basis=PriceBasis.FORWARD_ADJUSTED)
    backward = _bar(session, basis=PriceBasis.BACKWARD_ADJUSTED)
    assert {raw.logical_series_key, forward.logical_series_key, backward.logical_series_key} == {
        raw.logical_series_key,
        forward.logical_series_key,
        backward.logical_series_key,
    }
    assert len({raw.logical_series_key, forward.logical_series_key, backward.logical_series_key}) == 3


def test_placeholder_missing_and_provider_failure_are_typed_gaps_not_bars() -> None:
    capture = ProviderCapture(
        capture_id=uuid4(),
        provider_product_id=uuid4(),
        capture_key="tencent-2026-08-28-1455",
        request_hash="a" * 64,
        status=CaptureStatus.CAPTURED,
        temporal=_temporal(),
        artifact_id=uuid4(),
        error_code=None,
        limitation_code=None,
        payload_encoding="GB18030",
    )
    gap = SourceGap(
        gap_id=uuid4(),
        provider_product_id=capture.provider_product_id,
        capture_id=capture.capture_id,
        instrument_id=uuid4(),
        session_id=_session().session_id,
        gap_kind=GapKind.PLACEHOLDER,
        reason_code=GapReasonCode.NULL_OHLC_PLACEHOLDER,
        fact_kind=GapFactKind.MARKET_BAR,
        instrument_fact_kind=None,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=_at(6, 50),
        event_end=_at(6, 55),
        detail="exact response bytes are retained by the Capture Artifact",
    )
    batch = NormalizationBatch(
        source_capture_id=capture.capture_id,
        source_provider_product_id=capture.provider_product_id,
        gaps=(gap,),
    )
    assert batch.bars == ()
    assert batch.gaps == (gap,)
    with pytest.raises(ValueError, match="OHLC and exact-bar reasons"):
        replace(
            gap,
            fact_kind=GapFactKind.INSTRUMENT,
            timeframe=None,
            price_basis=None,
        )
    with pytest.raises(ValueError, match="ProviderProduct"):
        NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            gaps=(replace(gap, provider_product_id=uuid4()),),
        )


def test_generic_bar_and_status_types_keep_exact_scope_basis_and_session_separate() -> None:
    session = _session()
    raw = _bar(session)
    prior_status = SecurityStatusFactRevision(
        fact_revision_id=uuid4(),
        provider_product_id=raw.provider_product_id,
        capture_id=raw.capture_id,
        instrument_id=raw.instrument_id,
        session_id=uuid4(),
        evidence_scope=EvidenceScope.PRIOR_SESSION,
        status=SecurityStatus.SUSPENDED,
        event_start=session.open_at - timedelta(days=1),
        event_end=session.close_at - timedelta(days=1),
        revision=1,
        supersedes_revision_id=None,
    )
    adjusted = _bar(session, basis=PriceBasis.FORWARD_ADJUSTED)
    prior = MarketBarRevision(
        bar_revision_id=uuid4(),
        provider_product_id=raw.provider_product_id,
        capture_id=raw.capture_id,
        instrument_id=raw.instrument_id,
        session_id=uuid4(),
        timeframe=BarTimeframe.DAILY,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=session.open_at - timedelta(days=1),
        event_end=session.close_at - timedelta(days=1),
        revision=1,
        supersedes_revision_id=None,
        open=_cny("10"),
        high=_cny("10"),
        low=_cny("10"),
        close=_cny("10"),
        volume=_shares("0"),
        turnover=None,
    )
    assert raw.timeframe is BarTimeframe.MINUTE_5
    assert raw.price_basis is PriceBasis.RAW_UNADJUSTED
    assert raw.session_id == session.session_id
    assert adjusted.price_basis is PriceBasis.FORWARD_ADJUSTED
    assert prior.timeframe is BarTimeframe.DAILY
    assert prior.session_id != session.session_id
    assert prior_status.evidence_scope is EvidenceScope.PRIOR_SESSION
    assert prior_status.status is SecurityStatus.SUSPENDED


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (
            GapKind.MISSING,
            GapReasonCode.EXPECTED_OBSERVATION_MISSING,
        ),
        (
            GapKind.PLACEHOLDER,
            GapReasonCode.NULL_OHLC_PLACEHOLDER,
        ),
        (
            GapKind.PROVIDER_FAILURE,
            GapReasonCode.PROVIDER_FAILURE,
        ),
        (
            GapKind.CONFLICT,
            GapReasonCode.CONFLICTING_SOURCE_REVISIONS,
        ),
        (
            GapKind.INVALID_OHLC,
            GapReasonCode.INVALID_OHLC,
        ),
    ],
)
def test_gap_class_preserves_generic_source_semantics_without_target_resolution(
    kind: GapKind,
    reason: GapReasonCode,
) -> None:
    session = _session()
    raw = _bar(session)
    gap = SourceGap(
        gap_id=uuid4(),
        provider_product_id=raw.provider_product_id,
        capture_id=raw.capture_id,
        instrument_id=raw.instrument_id,
        session_id=session.session_id,
        gap_kind=kind,
        reason_code=reason,
        fact_kind=GapFactKind.MARKET_BAR,
        instrument_fact_kind=None,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=raw.event_start,
        event_end=raw.event_end,
        detail=None,
    )
    assert gap.gap_kind is kind
    assert gap.reason_code is reason
    assert gap.fact_kind is GapFactKind.MARKET_BAR
    assert gap.timeframe is BarTimeframe.MINUTE_5
    assert gap.price_basis is PriceBasis.RAW_UNADJUSTED


def test_revision_roots_and_normalization_evidence_are_explicit() -> None:
    session = _session()
    raw = _bar(session)
    with pytest.raises(ValueError, match="revision chain"):
        replace(_bar(session), revision=2, supersedes_revision_id=None)
    with pytest.raises(ValueError, match="fact revision or typed SourceGap"):
        NormalizationBatch(
            source_capture_id=uuid4(),
            source_provider_product_id=uuid4(),
        )
    missing = SourceGap(
        gap_id=uuid4(),
        provider_product_id=raw.provider_product_id,
        capture_id=raw.capture_id,
        instrument_id=raw.instrument_id,
        session_id=raw.session_id,
        gap_kind=GapKind.MISSING,
        reason_code=GapReasonCode.EXACT_BAR_MISSING,
        fact_kind=GapFactKind.MARKET_BAR,
        instrument_fact_kind=None,
        timeframe=raw.timeframe,
        price_basis=raw.price_basis,
        event_start=raw.event_start,
        event_end=raw.event_end,
        detail=None,
    )
    with pytest.raises(ValueError, match="one SourceGap disposition"):
        NormalizationBatch(
            source_capture_id=raw.capture_id,
            source_provider_product_id=raw.provider_product_id,
            gaps=(
                missing,
                replace(
                    missing,
                    gap_id=uuid4(),
                    gap_kind=GapKind.PLACEHOLDER,
                    reason_code=GapReasonCode.NULL_OHLC_PLACEHOLDER,
                ),
            ),
        )


def test_financial_values_match_the_full_postgres_precision_boundary() -> None:
    money = Money(Decimal("99999999999999999999.1234567890"), "CNY")
    quantity = Quantity(
        Decimal("9999999999999999999999999999.1234567890"),
        QuantityUnit.SHARES,
    )
    assert money.amount == Decimal("99999999999999999999.1234567890")
    assert quantity.amount == Decimal(
        "9999999999999999999999999999.1234567890"
    )
    with pytest.raises(ValueError, match="scale"):
        Money(Decimal("1.00000000001"), "CNY")
    with pytest.raises(ValueError, match="precision"):
        Quantity(Decimal("10000000000000000000000000000"), QuantityUnit.SHARES)
