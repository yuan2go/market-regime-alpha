"""Evidence-derived Xuntou PIT v4 mappings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from market_regime_alpha.research.xuntou_pit_v4_contract import ResearchOrderabilityStatus


@dataclass(frozen=True, slots=True)
class ResearchOrderabilityDecision:
    status: ResearchOrderabilityStatus
    reason: str


@dataclass(frozen=True, slots=True)
class EvaluationEvidenceDecision:
    primary_1030_available: bool
    path_diagnostics_available: bool
    reasons: tuple[str, ...]


def qualify_evaluation_evidence(
    *,
    has_exact_1030_minute: bool,
    minute_path_0930_1030_complete: bool,
    full_diagnostic_path_complete: bool,
    daily_close_available: bool,
) -> EvaluationEvidenceDecision:
    reasons: list[str] = []
    if not has_exact_1030_minute or not minute_path_0930_1030_complete:
        reasons.append("NEXT_SESSION_1030_MINUTE_EVIDENCE_REQUIRED")
    if not full_diagnostic_path_complete:
        reasons.append("PATH_DIAGNOSTICS_UNAVAILABLE")
    if daily_close_available and not has_exact_1030_minute:
        reasons.append("DAILY_CLOSE_CANNOT_SUBSTITUTE_FOR_1030")
    return EvaluationEvidenceDecision(
        primary_1030_available=has_exact_1030_minute and minute_path_0930_1030_complete,
        path_diagnostics_available=full_diagnostic_path_complete,
        reasons=tuple(reasons),
    )


def derive_research_orderability(
    *,
    decision_time: datetime,
    quote_observed_at: datetime | None,
    available_at: datetime,
    snapshot_finalized: bool,
    trading_status: str,
    suspension_status: str,
    reference_price: float | None,
    best_ask_price: float | None,
    best_ask_volume: float | None,
    best_bid_price: float | None,
    best_bid_volume: float | None,
    limit_up_price: float | None,
    limit_down_price: float | None,
) -> ResearchOrderabilityDecision:
    if trading_status in {"SUSPENDED", "CLOSED", "HALTED"} or suspension_status == "SUSPENDED":
        return ResearchOrderabilityDecision(ResearchOrderabilityStatus.NOT_ORDERABLE, "CONFIRMED_NOT_TRADING")
    if quote_observed_at != decision_time or available_at > decision_time:
        return ResearchOrderabilityDecision(ResearchOrderabilityStatus.UNKNOWN, "DECISION_TIME_QUOTE_UNAVAILABLE")
    values = (
        reference_price,
        best_ask_price,
        best_ask_volume,
        best_bid_price,
        best_bid_volume,
        limit_up_price,
        limit_down_price,
    )
    if not snapshot_finalized or any(
        value is None or not math.isfinite(value) or value <= 0 for value in values
    ):
        return ResearchOrderabilityDecision(ResearchOrderabilityStatus.UNKNOWN, "ORDER_BOOK_EVIDENCE_INCOMPLETE")
    assert reference_price is not None and best_ask_price is not None
    assert limit_up_price is not None and limit_down_price is not None
    if not limit_down_price <= reference_price <= limit_up_price or best_ask_price >= limit_up_price:
        return ResearchOrderabilityDecision(ResearchOrderabilityStatus.NOT_ORDERABLE, "PRICE_LIMIT_OR_INVALID_MARK")
    if trading_status != "TRADING" or suspension_status != "NOT_SUSPENDED":
        return ResearchOrderabilityDecision(ResearchOrderabilityStatus.UNKNOWN, "TRADING_STATUS_UNVERIFIED")
    return ResearchOrderabilityDecision(
        ResearchOrderabilityStatus.RESEARCH_ORDERABLE,
        "DECISION_TIME_NORMAL_BUY_INTENT_ALLOWED",
    )
