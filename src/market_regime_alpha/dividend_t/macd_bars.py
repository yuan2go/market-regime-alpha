"""Formal closed-bar and point-in-time price preparation for MACD."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Iterable

from market_regime_alpha.dividend_t.macd import (
    MACDConfig,
    MACDDataReason,
    MACDResult,
    calculate_macd,
    neutral_macd_result,
)


class MACDBarContractError(ValueError):
    """Raised when bar timing or finalized-state semantics are ambiguous."""


class PriceAdjustmentUnavailable(ValueError):
    """Raised when a point-in-time adjustment cannot be applied safely."""


@dataclass(frozen=True)
class CorporateAction:
    effective_time: Any
    share_factor: float = 1.0
    cash_per_share: float = 0.0


@dataclass(frozen=True)
class PreparedMACDBars:
    config: MACDConfig
    frame: Any
    adjusted_closes: tuple[float, ...]
    data_reason: MACDDataReason
    missing_bar_times: tuple[Any, ...]
    provisional_excluded_count: int
    last_closed_bar_time: Any | None


def prepare_macd_bars(
    frame: Any,
    *,
    config: MACDConfig,
    evaluation_time: Any,
    corporate_actions: Iterable[CorporateAction],
    adjustment_data_complete: bool,
    expected_bar_times: tuple[Any, ...],
    suspension_times: frozenset[Any],
) -> PreparedMACDBars:
    """Validate, close-filter, gap-check, and point-in-time adjust bars.

    ``expected_bar_times`` is the caller's exchange-calendar contract for the
    entire supplied feature history. It must contain interval-end timestamps,
    not bucket starts. The function never infers finalized status and never
    forward-fills a missing interval.
    """

    import pandas as pd

    if not isinstance(config, MACDConfig):
        raise MACDBarContractError("formal bar preparation requires a MACDConfig")
    if not isinstance(adjustment_data_complete, bool):
        raise MACDBarContractError("adjustment_data_complete must be boolean")
    if not hasattr(frame, "columns"):
        raise MACDBarContractError("formal MACD bars must be a tabular frame")

    required = {"timestamp", "close", "bar_final"}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        raise MACDBarContractError(f"formal MACD bars missing required fields: {', '.join(missing_columns)}")

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    if data["timestamp"].isna().any():
        raise MACDBarContractError("bar timestamp must be a valid interval-end time")
    if data["timestamp"].duplicated().any():
        raise MACDBarContractError("duplicate bar timestamp is not allowed")
    if data["bar_final"].isna().any() or not pd.api.types.is_bool_dtype(data["bar_final"].dtype):
        raise MACDBarContractError("bar_final must contain explicit boolean source status")

    evaluation = _timestamp(evaluation_time, label="evaluation_time")
    expected = _unique_timestamps(expected_bar_times, label="expected_bar_times")
    suspended = frozenset(_timestamp(value, label="suspension_times") for value in suspension_times)
    expected_set = frozenset(expected)

    data = data.sort_values("timestamp").reset_index(drop=True)
    eligible_mask = data["bar_final"] & (data["timestamp"] <= evaluation)
    closed = data.loc[eligible_mask].copy()
    unexpected = tuple(timestamp for timestamp in closed["timestamp"] if timestamp not in expected_set)
    if unexpected:
        raise MACDBarContractError(f"unexpected finalized bar timestamp outside interval-end calendar: {unexpected[0]}")

    expected_closed = tuple(timestamp for timestamp in expected if timestamp <= evaluation)
    actual_times = frozenset(closed["timestamp"])
    missing_bar_times = tuple(
        timestamp for timestamp in expected_closed if timestamp not in actual_times and timestamp not in suspended
    )
    data_reason = MACDDataReason.EXPECTED_BAR_MISSING if missing_bar_times else MACDDataReason.READY

    raw_closes = _coerce_raw_closes(closed["close"])
    if raw_closes is None:
        adjusted_closes: tuple[float, ...] = ()
        data_reason = MACDDataReason.INVALID_CLOSE
    elif not adjustment_data_complete:
        adjusted_closes = ()
        data_reason = MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    else:
        try:
            adjusted_closes = _point_in_time_adjusted_closes(
                raw_closes,
                tuple(closed["timestamp"]),
                tuple(corporate_actions),
                evaluation,
            )
        except PriceAdjustmentUnavailable:
            adjusted_closes = ()
            data_reason = MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE

    last_closed_bar_time = closed["timestamp"].iloc[-1] if len(closed) else None
    return PreparedMACDBars(
        config=config,
        frame=closed,
        adjusted_closes=adjusted_closes,
        data_reason=data_reason,
        missing_bar_times=missing_bar_times,
        provisional_excluded_count=int((~eligible_mask).sum()),
        last_closed_bar_time=last_closed_bar_time,
    )


def calculate_macd_from_bars(prepared: PreparedMACDBars, config: MACDConfig) -> MACDResult:
    """Calculate MACD only when bar and price preparation is formally ready."""

    if prepared.config != config:
        raise MACDBarContractError("prepared bars and calculation must use the same MACDConfig")
    if prepared.data_reason is MACDDataReason.READY:
        result = calculate_macd(prepared.adjusted_closes, config)
    else:
        result = neutral_macd_result(config, prepared.data_reason)
    return replace(
        result,
        provisional=False,
        last_closed_bar_time=str(prepared.last_closed_bar_time) if prepared.last_closed_bar_time is not None else None,
    )


def expected_a_share_5m_closes(day: Any) -> tuple[Any, ...]:
    """Return the 48 continuous-auction five-minute interval ends."""

    import pandas as pd

    date = _timestamp(day, label="session day").normalize()
    morning = pd.date_range(
        date + pd.Timedelta(hours=9, minutes=35),
        date + pd.Timedelta(hours=11, minutes=30),
        freq="5min",
    )
    afternoon = pd.date_range(
        date + pd.Timedelta(hours=13, minutes=5),
        date + pd.Timedelta(hours=15),
        freq="5min",
    )
    return tuple((*morning, *afternoon))


def _timestamp(value: Any, *, label: str) -> Any:
    import pandas as pd

    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise MACDBarContractError(f"{label} must contain valid timestamps") from exc
    if pd.isna(timestamp):
        raise MACDBarContractError(f"{label} must contain valid timestamps")
    return timestamp


def _unique_timestamps(values: Iterable[Any], *, label: str) -> tuple[Any, ...]:
    timestamps = tuple(_timestamp(value, label=label) for value in values)
    if len(timestamps) != len(set(timestamps)):
        raise MACDBarContractError(f"{label} cannot contain duplicate timestamps")
    return tuple(sorted(timestamps))


def _coerce_raw_closes(values: Iterable[Any]) -> tuple[float, ...] | None:
    output: list[float] = []
    for value in values:
        if isinstance(value, bool):
            return None
        try:
            close = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(close) or close <= 0.0:
            return None
        output.append(close)
    return tuple(output)


def _point_in_time_adjusted_closes(
    raw_closes: tuple[float, ...],
    timestamps: tuple[Any, ...],
    actions: tuple[CorporateAction, ...],
    evaluation_time: Any,
) -> tuple[float, ...]:
    """Rebase prior closes using only actions effective by evaluation time."""

    normalized_actions: list[tuple[Any, CorporateAction]] = []
    for action in actions:
        if not isinstance(action, CorporateAction):
            raise PriceAdjustmentUnavailable("corporate action has an invalid contract")
        try:
            effective = _timestamp(action.effective_time, label="corporate action effective_time")
        except MACDBarContractError as exc:
            raise PriceAdjustmentUnavailable(str(exc)) from exc
        normalized_actions.append((effective, action))

    values = list(raw_closes)
    for effective, action in sorted(normalized_actions, key=lambda item: item[0]):
        if effective > evaluation_time:
            continue
        if isinstance(action.share_factor, bool) or isinstance(action.cash_per_share, bool):
            raise PriceAdjustmentUnavailable("corporate action values must be numeric")
        try:
            share_factor = float(action.share_factor)
            cash_per_share = float(action.cash_per_share)
        except (OverflowError, TypeError, ValueError) as exc:
            raise PriceAdjustmentUnavailable("corporate action values must be numeric") from exc
        if not math.isfinite(share_factor) or share_factor <= 0.0:
            raise PriceAdjustmentUnavailable("corporate action share factor must be finite and positive")
        if not math.isfinite(cash_per_share) or cash_per_share < 0.0:
            raise PriceAdjustmentUnavailable("corporate action cash amount must be finite and non-negative")
        for index, timestamp in enumerate(timestamps):
            if timestamp < effective:
                values[index] = (values[index] - cash_per_share) / share_factor

    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise PriceAdjustmentUnavailable("adjusted close must be finite and positive")
    return tuple(values)
