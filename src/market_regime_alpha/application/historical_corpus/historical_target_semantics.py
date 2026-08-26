"""Historical adapter for the frozen Target semantic specification.

The adapter is a pure function over already reloaded Normalized bars. Callers
must load those bars independently from their own owner path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.research_evaluation.target_semantics import (
    BarrierOrderingOutcome,
    TargetSemanticResult,
    TargetSemanticSpecification,
    TargetSemanticStatus,
)
from market_regime_alpha.application.research_evaluation.targets import (
    BarrierDefinition,
    OutcomeCheckpoint,
    TargetDefinition,
)
from market_regime_alpha.market_data.contracts import Timeframe


def evaluate_historical_target_semantics(
    *,
    specification: TargetSemanticSpecification,
    target: TargetDefinition,
    symbol: str,
    decision_time: datetime,
    next_session_date: date,
    source_bars: tuple[HistoricalNormalizedBar, ...],
) -> TargetSemanticResult:
    """Resolve one Target without a Daily/last-observation price fallback."""

    if decision_time.tzinfo is None or decision_time.utcoffset() is None:
        raise ValueError("DecisionTime must be timezone-aware")
    if target.canonical_horizon.session_offset != 1:
        raise ValueError("correctness Target requires session offset one")
    zone = ZoneInfo(specification.timezone_name)
    local_decision = decision_time.astimezone(zone)
    if local_decision.time().replace(tzinfo=None) != _parse_time(
        specification.decision_reference_local_time
    ):
        raise ValueError("DecisionTime disagrees with Target semantics")
    if next_session_date <= local_decision.date():
        raise ValueError("Target session must follow the Decision session")
    relevant_bars = tuple(item for item in source_bars if item.symbol == symbol)
    for item in relevant_bars:
        item.verify_identity()

    exact_decision = tuple(
        sorted(
            (
                item
                for item in relevant_bars
                if item.market_date == local_decision.date()
                and item.timeframe is Timeframe.MINUTE_5
                and item.event_end == decision_time
            ),
            key=_bar_key,
        )
    )
    reasons: set[str] = set()
    decision_status, decision_price = _decision_reference(
        exact_decision,
        specification=specification,
        reasons=reasons,
    )
    diagnostics = (
        ()
        if decision_status is TargetSemanticStatus.COMPLETE
        else _diagnostic_bars(
            relevant_bars,
            decision_time=decision_time,
            exact_decision=exact_decision,
            reasons=reasons,
        )
    )

    outcome_start_local = datetime.combine(
        next_session_date,
        _parse_time(specification.outcome_window_start_local_time),
        zone,
    )
    expected_grid = _expected_grid(
        next_session_date,
        checkpoint=target.checkpoint,
        zone=zone,
    )
    outcome_candidates = _outcome_candidates(
        relevant_bars,
        next_session_date=next_session_date,
        expected_grid=expected_grid,
        checkpoint=target.checkpoint,
        zone=zone,
    )
    outcome_status, valid_outcome, outcome_failed = _outcome_window(
        outcome_candidates,
        expected_grid=expected_grid,
        specification=specification,
        reasons=reasons,
    )
    checkpoint_status, checkpoint_price = _checkpoint_observation(
        valid_outcome,
        checkpoint=target.checkpoint,
        expected_grid=expected_grid,
        outcome_failed=outcome_failed,
    )

    checkpoint_return_status = _derived_status(
        decision_status, checkpoint_status
    )
    checkpoint_return = (
        None
        if checkpoint_return_status is not TargetSemanticStatus.COMPLETE
        else _return(checkpoint_price, decision_price)
    )
    path_metric_status = _derived_status(decision_status, outcome_status)
    if path_metric_status is not TargetSemanticStatus.COMPLETE:
        mfe = None
        mae = None
    else:
        assert decision_price is not None
        mfe = (
            max(_required_price(item.high) for item in valid_outcome)
            - decision_price
        ) / decision_price
        mae = (
            min(_required_price(item.low) for item in valid_outcome)
            - decision_price
        ) / decision_price
    barrier_status, barrier_passages, barrier_ordering = _barriers(
        target.barriers,
        bars=valid_outcome,
        decision_price=decision_price,
        dependency_status=path_metric_status,
    )
    if barrier_ordering is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE:
        reasons.add("BARRIER_ORDERING_NOT_OBSERVABLE")
    if decision_status is not TargetSemanticStatus.COMPLETE:
        reasons.add("DERIVED_DECISION_REFERENCE_UNAVAILABLE")
    if outcome_status is not TargetSemanticStatus.COMPLETE:
        reasons.add("DERIVED_OUTCOME_WINDOW_INCOMPLETE")

    return TargetSemanticResult(
        semantic_specification=specification.reference,
        symbol=symbol,
        decision_time=decision_time,
        target_session=next_session_date,
        outcome_window_start=outcome_start_local.astimezone(UTC),
        # OPEN is observed through the first 5-minute source bar.  Its Target
        # reference is 09:30, while the independently observable path ends at
        # 09:35.  Other frozen checkpoints already coincide with grid end.
        outcome_window_end=expected_grid[-1][1],
        expected_outcome_bar_count=len(expected_grid),
        observed_outcome_bar_count=len(valid_outcome),
        decision_reference_status=decision_status,
        outcome_window_status=outcome_status,
        checkpoint_observation_status=checkpoint_status,
        checkpoint_return_status=checkpoint_return_status,
        mfe_status=path_metric_status,
        mae_status=path_metric_status,
        barrier_status=barrier_status,
        decision_reference_price=decision_price,
        checkpoint_price=checkpoint_price,
        checkpoint_return=checkpoint_return,
        mfe=mfe,
        mae=mae,
        barrier_passages=barrier_passages,
        barrier_ordering=barrier_ordering,
        decision_source_references=tuple(item.reference for item in exact_decision),
        outcome_source_references=tuple(
            item.reference for item in sorted(outcome_candidates, key=_bar_key)
        ),
        diagnostic_source_references=tuple(
            item.reference for item in diagnostics
        ),
        reason_codes=tuple(sorted(reasons)),
    )


def apply_raw_corporate_action_conflict(
    result: TargetSemanticResult,
    *,
    target: TargetDefinition,
    reason_code: str,
) -> TargetSemanticResult:
    """Fail dependent metrics while retaining the independently observed path."""

    return replace(
        result,
        checkpoint_return_status=TargetSemanticStatus.FAILED,
        mfe_status=TargetSemanticStatus.FAILED,
        mae_status=TargetSemanticStatus.FAILED,
        barrier_status=TargetSemanticStatus.FAILED,
        checkpoint_return=None,
        mfe=None,
        mae=None,
        barrier_passages=tuple((item.barrier_id, None) for item in target.barriers),
        barrier_ordering=BarrierOrderingOutcome.NOT_APPLICABLE,
        reason_codes=tuple(
            sorted(
                {
                    *result.reason_codes,
                    "CORPORATE_ACTION_POLICY_FAILED_CLOSED",
                    "CORPORATE_ACTION_RAW_POLICY_CONFLICT",
                    reason_code,
                }
            )
        ),
    )


def _decision_reference(
    exact: tuple[HistoricalNormalizedBar, ...],
    *,
    specification: TargetSemanticSpecification,
    reasons: set[str],
) -> tuple[TargetSemanticStatus, Decimal | None]:
    if not exact:
        reasons.add("DECISION_EXACT_1455_BAR_MISSING")
        return TargetSemanticStatus.UNAVAILABLE, None
    if len(exact) != 1 or len({item.reference for item in exact}) != len(exact):
        reasons.add("DECISION_EXACT_1455_SOURCE_CONFLICT")
        return TargetSemanticStatus.FAILED, None
    item = exact[0]
    if item.adjustment_basis not in specification.accepted_raw_adjustment_bases:
        reasons.add("CORPORATE_ACTION_RAW_POLICY_CONFLICT")
        return TargetSemanticStatus.FAILED, None
    prices = (item.open, item.high, item.low, item.close)
    if any(value is None for value in prices):
        reasons.add("DECISION_EXACT_1455_BAR_UNPRICED_PLACEHOLDER")
        if item.trading_status is HistoricalTradingStatus.SUSPENDED:
            reasons.add("DECISION_EXACT_1455_BAR_SUSPENDED")
        return TargetSemanticStatus.UNAVAILABLE, None
    if item.trading_status is HistoricalTradingStatus.SUSPENDED:
        reasons.add("DECISION_EXACT_1455_BAR_SUSPENDED")
        return TargetSemanticStatus.UNAVAILABLE, None
    assert item.open is not None
    assert item.high is not None
    assert item.low is not None
    assert item.close is not None
    if (
        any(not value.is_finite() or value <= 0 for value in prices if value is not None)
        or item.high < max(item.open, item.low, item.close)
        or item.low > min(item.open, item.high, item.close)
    ):
        reasons.add("DECISION_EXACT_1455_PRICE_STRUCTURE_INVALID")
        return TargetSemanticStatus.FAILED, None
    return TargetSemanticStatus.COMPLETE, item.close


def _diagnostic_bars(
    bars: tuple[HistoricalNormalizedBar, ...],
    *,
    decision_time: datetime,
    exact_decision: tuple[HistoricalNormalizedBar, ...],
    reasons: set[str],
) -> tuple[HistoricalNormalizedBar, ...]:
    exact_references = {item.reference for item in exact_decision}
    daily = tuple(
        sorted(
            (
                item
                for item in bars
                if item.timeframe is Timeframe.DAILY
                and item.event_end <= decision_time
                and item.close is not None
            ),
            key=_bar_key,
        )
    )
    intraday = tuple(
        sorted(
            (
                item
                for item in bars
                if item.timeframe is Timeframe.MINUTE_5
                and item.event_end < decision_time
                and item.reference not in exact_references
                and item.close is not None
            ),
            key=_bar_key,
        )
    )
    diagnostics: list[HistoricalNormalizedBar] = []
    if daily:
        diagnostics.append(daily[-1])
        reasons.add("DIAGNOSTIC_PREVIOUS_SESSION_DAILY_CLOSE_IGNORED")
    if intraday:
        diagnostics.append(intraday[-1])
        reasons.add("DIAGNOSTIC_LAST_AVAILABLE_BAR_IGNORED")
    return tuple(
        sorted(
            {item.reference: item for item in diagnostics}.values(),
            key=_bar_key,
        )
    )


def _outcome_candidates(
    bars: tuple[HistoricalNormalizedBar, ...],
    *,
    next_session_date: date,
    expected_grid: tuple[tuple[datetime, datetime], ...],
    checkpoint: OutcomeCheckpoint,
    zone: ZoneInfo,
) -> tuple[HistoricalNormalizedBar, ...]:
    if checkpoint is OutcomeCheckpoint.OPEN:
        open_time = datetime.combine(next_session_date, time(9, 30), zone).astimezone(
            UTC
        )
        return tuple(
            item
            for item in bars
            if item.market_date == next_session_date
            and item.timeframe is Timeframe.MINUTE_5
            and item.event_start == open_time
        )
    window_start = expected_grid[0][0]
    window_end = expected_grid[-1][1]
    return tuple(
        item
        for item in bars
        if item.market_date == next_session_date
        and item.timeframe is Timeframe.MINUTE_5
        and item.event_start < window_end
        and item.event_end > window_start
    )


def _outcome_window(
    candidates: tuple[HistoricalNormalizedBar, ...],
    *,
    expected_grid: tuple[tuple[datetime, datetime], ...],
    specification: TargetSemanticSpecification,
    reasons: set[str],
) -> tuple[
    TargetSemanticStatus, tuple[HistoricalNormalizedBar, ...], bool
]:
    by_interval: defaultdict[
        tuple[datetime, datetime], list[HistoricalNormalizedBar]
    ] = defaultdict(list)
    for item in candidates:
        by_interval[(item.event_start, item.event_end)].append(item)
    expected = set(expected_grid)
    failed = any(key not in expected for key in by_interval) or any(
        len(values) != 1 for values in by_interval.values()
    )
    if any(
        item.adjustment_basis not in specification.accepted_raw_adjustment_bases
        for item in candidates
    ):
        failed = True
        reasons.add("CORPORATE_ACTION_RAW_POLICY_CONFLICT")
    valid = tuple(
        values[0]
        for key in expected_grid
        if len((values := by_interval.get(key, []))) == 1
        and values[0].open is not None
        and values[0].high is not None
        and values[0].low is not None
        and values[0].close is not None
        and values[0].trading_status is not HistoricalTradingStatus.SUSPENDED
        and values[0].adjustment_basis
        in specification.accepted_raw_adjustment_bases
    )
    if failed:
        reasons.add("OUTCOME_SOURCE_CONFLICT")
        return TargetSemanticStatus.FAILED, valid, True
    if len(valid) == len(expected_grid):
        reasons.add("OUTCOME_GRID_COMPLETE")
        return TargetSemanticStatus.COMPLETE, valid, False
    if valid:
        reasons.add("OUTCOME_GRID_PARTIAL")
        return TargetSemanticStatus.PARTIAL, valid, False
    reasons.add("OUTCOME_GRID_EMPTY")
    return TargetSemanticStatus.UNAVAILABLE, (), False


def _checkpoint_observation(
    valid_bars: tuple[HistoricalNormalizedBar, ...],
    *,
    checkpoint: OutcomeCheckpoint,
    expected_grid: tuple[tuple[datetime, datetime], ...],
    outcome_failed: bool,
) -> tuple[TargetSemanticStatus, Decimal | None]:
    if outcome_failed:
        return TargetSemanticStatus.FAILED, None
    if not valid_bars:
        return TargetSemanticStatus.UNAVAILABLE, None
    expected_interval = expected_grid[0] if checkpoint is OutcomeCheckpoint.OPEN else expected_grid[-1]
    matches = tuple(
        item
        for item in valid_bars
        if (item.event_start, item.event_end) == expected_interval
    )
    if len(matches) != 1:
        return TargetSemanticStatus.UNAVAILABLE, None
    value = matches[0].open if checkpoint is OutcomeCheckpoint.OPEN else matches[0].close
    if value is None:
        return TargetSemanticStatus.UNAVAILABLE, None
    return TargetSemanticStatus.COMPLETE, value


def _derived_status(
    *dependencies: TargetSemanticStatus,
) -> TargetSemanticStatus:
    if any(item is TargetSemanticStatus.FAILED for item in dependencies):
        return TargetSemanticStatus.FAILED
    if all(item is TargetSemanticStatus.COMPLETE for item in dependencies):
        return TargetSemanticStatus.COMPLETE
    return TargetSemanticStatus.UNAVAILABLE


def _return(price: Decimal | None, reference: Decimal | None) -> Decimal:
    assert price is not None and reference is not None
    return (price - reference) / reference


def _barriers(
    barriers: tuple[BarrierDefinition, ...],
    *,
    bars: tuple[HistoricalNormalizedBar, ...],
    decision_price: Decimal | None,
    dependency_status: TargetSemanticStatus,
) -> tuple[
    TargetSemanticStatus,
    tuple[tuple[str, datetime | None], ...],
    BarrierOrderingOutcome,
]:
    if dependency_status is not TargetSemanticStatus.COMPLETE:
        status = (
            TargetSemanticStatus.FAILED
            if dependency_status is TargetSemanticStatus.FAILED
            else TargetSemanticStatus.UNAVAILABLE
        )
        return status, tuple((item.barrier_id, None) for item in barriers), (
            BarrierOrderingOutcome.NOT_APPLICABLE
        )
    assert decision_price is not None
    passages = tuple(
        (
            barrier.barrier_id,
            _first_passage(bars, decision_price, barrier),
        )
        for barrier in barriers
    )
    ordering = _barrier_ordering(passages, barriers)
    status = (
        TargetSemanticStatus.PARTIAL
        if ordering is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
        else TargetSemanticStatus.COMPLETE
    )
    return status, passages, ordering


def _first_passage(
    bars: tuple[HistoricalNormalizedBar, ...],
    reference: Decimal,
    barrier: BarrierDefinition,
) -> datetime | None:
    boundary = reference * (
        Decimal("1") + barrier.return_threshold
        if barrier.direction == "UP"
        else Decimal("1") - barrier.return_threshold
    )
    for item in bars:
        high = _required_price(item.high)
        low = _required_price(item.low)
        if (barrier.direction == "UP" and high >= boundary) or (
            barrier.direction == "DOWN" and low <= boundary
        ):
            return item.event_end
    return None


def _barrier_ordering(
    passages: tuple[tuple[str, datetime | None], ...],
    barriers: tuple[BarrierDefinition, ...],
) -> BarrierOrderingOutcome:
    passage_by_id = dict(passages)
    ups = tuple(
        passage_at
        for item in barriers
        if item.direction == "UP"
        and (passage_at := passage_by_id[item.barrier_id]) is not None
    )
    downs = tuple(
        passage_at
        for item in barriers
        if item.direction == "DOWN"
        and (passage_at := passage_by_id[item.barrier_id]) is not None
    )
    if not any(item.direction == "UP" for item in barriers) or not any(
        item.direction == "DOWN" for item in barriers
    ):
        return BarrierOrderingOutcome.NOT_APPLICABLE
    first_up = min(ups, default=None)
    first_down = min(downs, default=None)
    if first_up is None and first_down is None:
        return BarrierOrderingOutcome.NO_TOUCH
    if first_down is None:
        return BarrierOrderingOutcome.UP_FIRST
    if first_up is None:
        return BarrierOrderingOutcome.DOWN_FIRST
    if first_up == first_down:
        return BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
    return (
        BarrierOrderingOutcome.UP_FIRST
        if first_up < first_down
        else BarrierOrderingOutcome.DOWN_FIRST
    )


def _expected_grid(
    market_date: date,
    *,
    checkpoint: OutcomeCheckpoint,
    zone: ZoneInfo,
) -> tuple[tuple[datetime, datetime], ...]:
    if checkpoint is OutcomeCheckpoint.OPEN:
        start = datetime.combine(market_date, time(9, 30), zone).astimezone(UTC)
        return ((start, start + timedelta(minutes=5)),)
    end_time = _checkpoint_time(checkpoint)
    starts: list[time] = []
    cursor = datetime.combine(market_date, time(9, 30))
    end = datetime.combine(market_date, end_time)
    while cursor + timedelta(minutes=5) <= end:
        local_time = cursor.time()
        if local_time < time(11, 30) or local_time >= time(13, 0):
            starts.append(local_time)
        cursor += timedelta(minutes=5)
    return tuple(
        (
            datetime.combine(market_date, item, zone).astimezone(UTC),
            (
                datetime.combine(market_date, item, zone)
                + timedelta(minutes=5)
            ).astimezone(UTC),
        )
        for item in starts
    )


def _checkpoint_time(value: OutcomeCheckpoint) -> time:
    return {
        OutcomeCheckpoint.OPEN: time(9, 30),
        OutcomeCheckpoint.TIME_0945: time(9, 45),
        OutcomeCheckpoint.TIME_1000: time(10, 0),
        OutcomeCheckpoint.TIME_1030: time(10, 30),
        OutcomeCheckpoint.TIME_1130: time(11, 30),
        OutcomeCheckpoint.CLOSE: time(15, 0),
    }[value]


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def _required_price(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("complete Target path contains an unpriced bar")
    return value


def _bar_key(
    value: HistoricalNormalizedBar,
) -> tuple[datetime, datetime, str, str]:
    return (
        value.event_start,
        value.event_end,
        str(value.bar_id),
        value.content_hash,
    )


__all__ = [
    "apply_raw_corporate_action_conflict",
    "evaluate_historical_target_semantics",
]
