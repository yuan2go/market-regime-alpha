from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.market.domain import (
    AdjustmentBasis,
    BarTimeframe,
    CaptureStatus,
    DecisionReferenceStatus,
    GapKind,
    MarketBarRevision,
    NormalizationBatch,
    ProviderCapture,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SourceGap,
    TemporalEnvelope,
    TradingSession,
    classify_decision_reference,
)


UTC = timezone.utc


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 28, hour, minute, tzinfo=UTC)


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


def _bar(session: TradingSession, *, basis: AdjustmentBasis = AdjustmentBasis.RAW_UNADJUSTED) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=uuid4(),
        provider_product_id=uuid4(),
        capture_id=uuid4(),
        instrument_id=uuid4(),
        session_id=session.session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=basis,
        event_start=session.decision_reference_at - timedelta(minutes=5),
        event_end=session.decision_reference_at,
        revision=1,
        supersedes_revision_id=None,
        open=Decimal("10.10"),
        high=Decimal("10.30"),
        low=Decimal("10.00"),
        close=Decimal("10.20"),
        volume=Decimal("0"),
        turnover=Decimal("0"),
    )


def test_temporal_axes_remain_distinct_and_unqualified_visibility_is_known_time() -> None:
    temporal = _temporal()
    assert temporal.source_available_at is None
    assert temporal.source_availability_status is SourceAvailabilityStatus.UNKNOWN
    assert temporal.decision_visible_at == temporal.known_at
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


def test_financial_values_are_decimal_and_invalid_ohlc_never_becomes_a_bar() -> None:
    session = _session()
    assert _bar(session).volume == Decimal("0")

    with pytest.raises(TypeError, match="open must be Decimal"):
        replace(_bar(session), open=10.1)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="legal OHLC"):
        MarketBarRevision(
            bar_revision_id=uuid4(),
            provider_product_id=uuid4(),
            capture_id=uuid4(),
            instrument_id=uuid4(),
            session_id=session.session_id,
            timeframe=BarTimeframe.MINUTE_5,
            adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
            event_start=session.decision_reference_at - timedelta(minutes=5),
            event_end=session.decision_reference_at,
            revision=1,
            supersedes_revision_id=None,
            open=Decimal("10"),
            high=Decimal("9"),
            low=Decimal("8"),
            close=Decimal("10"),
            volume=Decimal("1"),
            turnover=None,
        )


def test_adjustment_bases_are_distinct_logical_series() -> None:
    session = _session()
    raw = _bar(session)
    forward = _bar(session, basis=AdjustmentBasis.FORWARD_ADJUSTED)
    backward = _bar(session, basis=AdjustmentBasis.BACKWARD_ADJUSTED)
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
        reason_code="NULL_OHLC_PLACEHOLDER",
        fact_kind="MARKET_BAR",
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=_at(6, 50),
        event_end=_at(6, 55),
        detail="exact response bytes are retained by the Capture Artifact",
    )
    batch = NormalizationBatch(source_capture_id=capture.capture_id, gaps=(gap,))
    assert batch.bars == ()
    assert batch.gaps == (gap,)


def test_exact_1455_reference_never_uses_previous_session_daily_or_adjusted_data() -> None:
    session = _session()
    raw = _bar(session)
    prior_status = SecurityStatusFactRevision(
        fact_revision_id=uuid4(),
        provider_product_id=raw.provider_product_id,
        capture_id=raw.capture_id,
        instrument_id=raw.instrument_id,
        session_id=uuid4(),
        evidence_scope="PRIOR_SESSION",
        status=SecurityStatus.SUSPENDED,
        event_start=session.open_at - timedelta(days=1),
        event_end=session.close_at - timedelta(days=1),
        revision=1,
        supersedes_revision_id=None,
    )
    available = classify_decision_reference(
        session=session,
        bar=raw,
        current_session_status=None,
        gap=None,
    )
    assert available.status is DecisionReferenceStatus.AVAILABLE

    explicit_suspension = classify_decision_reference(
        session=session,
        bar=raw,
        current_session_status=SecurityStatus.SUSPENDED,
        gap=None,
    )
    assert explicit_suspension.status is DecisionReferenceStatus.UNAVAILABLE
    assert explicit_suspension.reason_code == "CURRENT_SESSION_SUSPENDED"

    for invalid in (
        _bar(session, basis=AdjustmentBasis.FORWARD_ADJUSTED),
        MarketBarRevision(
            bar_revision_id=uuid4(),
            provider_product_id=raw.provider_product_id,
            capture_id=raw.capture_id,
            instrument_id=raw.instrument_id,
            session_id=uuid4(),
            timeframe=BarTimeframe.DAILY,
            adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
            event_start=session.open_at - timedelta(days=1),
            event_end=session.close_at - timedelta(days=1),
            revision=1,
            supersedes_revision_id=None,
            open=Decimal("10"),
            high=Decimal("10"),
            low=Decimal("10"),
            close=Decimal("10"),
            volume=Decimal("0"),
            turnover=None,
        ),
    ):
        result = classify_decision_reference(
            session=session,
            bar=invalid,
            current_session_status=prior_status.status if prior_status.evidence_scope == "DECISION_SESSION" else None,
            gap=None,
        )
        assert result.status is DecisionReferenceStatus.FAILED


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (GapKind.MISSING, DecisionReferenceStatus.UNAVAILABLE),
        (GapKind.PLACEHOLDER, DecisionReferenceStatus.UNAVAILABLE),
        (GapKind.PROVIDER_FAILURE, DecisionReferenceStatus.FAILED),
        (GapKind.CONFLICT, DecisionReferenceStatus.FAILED),
        (GapKind.INVALID_OHLC, DecisionReferenceStatus.FAILED),
    ],
)
def test_gap_class_controls_decision_reference_failure_semantics(
    kind: GapKind,
    expected: DecisionReferenceStatus,
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
        reason_code="TEST_GAP",
        fact_kind="MARKET_BAR",
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=raw.event_start,
        event_end=raw.event_end,
        detail=None,
    )
    result = classify_decision_reference(
        session=session,
        bar=None,
        current_session_status=None,
        gap=gap,
    )
    assert result.status is expected
