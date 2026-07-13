from __future__ import annotations

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.macd import BarInterval, MACDConfig, MACDDataReason
from market_regime_alpha.dividend_t.macd_bars import (
    CorporateAction,
    MACDBarContractError,
    PreparedMACDBars,
    calculate_macd_from_bars,
    expected_a_share_5m_closes,
    prepare_macd_bars,
)


def prepare(
    frame: pd.DataFrame,
    *,
    config: MACDConfig,
    evaluation_time: object,
    expected_bar_times: tuple[object, ...],
    corporate_actions: tuple[CorporateAction, ...] = (),
    adjustment_data_complete: bool = True,
    suspension_times: frozenset[object] = frozenset(),
) -> PreparedMACDBars:
    return prepare_macd_bars(
        frame,
        config=config,
        evaluation_time=evaluation_time,
        corporate_actions=corporate_actions,
        adjustment_data_complete=adjustment_data_complete,
        expected_bar_times=expected_bar_times,
        suspension_times=suspension_times,
    )


def test_formal_input_requires_explicit_finalized_source_status() -> None:
    frame = pd.DataFrame({"timestamp": ["2026-07-13 09:35:00"], "close": [10.0]})

    with pytest.raises(MACDBarContractError, match="bar_final"):
        prepare(
            frame,
            config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
            evaluation_time=pd.Timestamp("2026-07-13 09:35:00"),
            expected_bar_times=(pd.Timestamp("2026-07-13 09:35:00"),),
        )


def test_unclosed_five_minute_bar_is_excluded() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-07-13 09:35:00", "2026-07-13 09:40:00"],
            "close": [10.0, 10.1],
            "bar_final": [True, False],
        }
    )

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 09:39:59"),
        expected_bar_times=(pd.Timestamp("2026-07-13 09:35:00"),),
    )

    assert list(prepared.frame["timestamp"]) == [pd.Timestamp("2026-07-13 09:35:00")]
    assert prepared.adjusted_closes == (10.0,)
    assert prepared.provisional_excluded_count == 1
    assert prepared.last_closed_bar_time == pd.Timestamp("2026-07-13 09:35:00")


def test_bar_at_evaluation_time_still_requires_finalized_status() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-07-13 14:55:00", "2026-07-13 15:00:00"]),
            "close": [10.0, 10.1],
            "bar_final": [True, False],
        }
    )

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 15:00:00"),
        expected_bar_times=(pd.Timestamp("2026-07-13 14:55:00"),),
    )

    assert prepared.last_closed_bar_time == pd.Timestamp("2026-07-13 14:55:00")
    assert prepared.provisional_excluded_count == 1


def test_expected_missing_bar_is_not_forward_filled() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-07-13 09:35:00", "2026-07-13 09:45:00"],
            "close": [10.0, 10.2],
            "bar_final": [True, True],
        }
    )

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 09:45:00"),
        expected_bar_times=tuple(pd.to_datetime(["2026-07-13 09:35:00", "2026-07-13 09:40:00", "2026-07-13 09:45:00"])),
    )

    assert prepared.data_reason is MACDDataReason.EXPECTED_BAR_MISSING
    assert prepared.missing_bar_times == (pd.Timestamp("2026-07-13 09:40:00"),)
    assert len(prepared.frame) == 2
    assert prepared.adjusted_closes == (10.0, 10.2)


def test_verified_suspension_is_not_reported_as_gap() -> None:
    missing = pd.Timestamp("2026-07-13 10:00:00")
    expected = expected_a_share_5m_closes(pd.Timestamp("2026-07-13"))
    frame = pd.DataFrame(
        {
            "timestamp": [item for item in expected if item != missing],
            "close": [10.0] * (len(expected) - 1),
            "bar_final": [True] * (len(expected) - 1),
        }
    )

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        evaluation_time=pd.Timestamp("2026-07-13 15:00:00"),
        expected_bar_times=expected,
        suspension_times=frozenset({missing}),
    )

    assert prepared.data_reason is MACDDataReason.READY
    assert prepared.missing_bar_times == ()
    assert len(prepared.adjusted_closes) == 47


def test_start_labeled_or_auction_bar_is_rejected_by_interval_end_contract() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-07-13 09:30:00", "2026-07-13 09:35:00"],
            "close": [9.9, 10.0],
            "bar_final": [True, True],
        }
    )

    with pytest.raises(MACDBarContractError, match="unexpected finalized bar timestamp"):
        prepare(
            frame,
            config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
            evaluation_time=pd.Timestamp("2026-07-13 09:35:00"),
            expected_bar_times=(pd.Timestamp("2026-07-13 09:35:00"),),
        )


def test_duplicate_bar_timestamp_is_rejected() -> None:
    timestamp = pd.Timestamp("2026-07-13 09:35:00")
    frame = pd.DataFrame({"timestamp": [timestamp, timestamp], "close": [10.0, 10.1], "bar_final": [True, True]})

    with pytest.raises(MACDBarContractError, match="duplicate"):
        prepare(
            frame,
            config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
            evaluation_time=timestamp,
            expected_bar_times=(timestamp,),
        )


def test_a_share_session_has_no_lunch_or_overnight_placeholders() -> None:
    times = expected_a_share_5m_closes(pd.Timestamp("2026-07-13"))

    assert times[0].strftime("%H:%M") == "09:35"
    assert times[23].strftime("%H:%M") == "11:30"
    assert times[24].strftime("%H:%M") == "13:05"
    assert times[-1].strftime("%H:%M") == "15:00"
    assert all(not ("11:30" < item.strftime("%H:%M") < "13:05") for item in times)
    assert len(times) == 48


def test_point_in_time_split_adjustment_removes_false_jump() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-07-10 15:00", "2026-07-13 15:00"]),
            "close": [20.0, 10.1],
            "bar_final": [True, True],
        }
    )
    action = CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), share_factor=2.0, cash_per_share=0.0)

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=pd.Timestamp("2026-07-13 15:00"),
        corporate_actions=(action,),
        expected_bar_times=tuple(frame["timestamp"]),
    )

    assert prepared.adjusted_closes == pytest.approx((10.0, 10.1))


def test_cash_and_share_actions_are_applied_in_effective_time_order() -> None:
    times = pd.to_datetime(["2026-07-09 15:00", "2026-07-10 15:00", "2026-07-13 15:00"])
    frame = pd.DataFrame({"timestamp": times, "close": [22.0, 20.0, 10.0], "bar_final": [True, True, True]})
    actions = (
        CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), share_factor=2.0),
        CorporateAction(effective_time=pd.Timestamp("2026-07-10 09:30"), cash_per_share=2.0),
    )

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=times[-1],
        corporate_actions=actions,
        expected_bar_times=tuple(times),
    )

    assert prepared.adjusted_closes == pytest.approx((10.0, 10.0, 10.0))


def test_future_corporate_action_does_not_change_earlier_snapshot() -> None:
    times = pd.to_datetime(["2026-07-10 15:00", "2026-07-13 15:00"])
    frame = pd.DataFrame({"timestamp": times, "close": [10.0, 10.1], "bar_final": [True, True]})
    future = CorporateAction(effective_time=pd.Timestamp("2026-07-14 09:30"), share_factor=2.0)

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=times[-1],
        corporate_actions=(future,),
        expected_bar_times=tuple(times),
    )

    assert prepared.adjusted_closes == (10.0, 10.1)


def test_incomplete_corporate_action_source_blocks_formal_macd() -> None:
    timestamp = pd.Timestamp("2026-07-13 15:00:00")
    frame = pd.DataFrame({"timestamp": [timestamp], "close": [10.1], "bar_final": [True]})

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=timestamp,
        adjustment_data_complete=False,
        expected_bar_times=(timestamp,),
    )
    result = calculate_macd_from_bars(prepared, MACDConfig(bar_interval=BarInterval.DAY_1))

    assert prepared.data_reason is MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    assert prepared.adjusted_closes == ()
    assert result.data_reason is MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    assert result.data_ready is False


@pytest.mark.parametrize(
    "action",
    [
        CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), share_factor=0.0),
        CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), share_factor=float("nan")),
        CorporateAction(effective_time=pd.Timestamp("2026-07-13 09:30"), cash_per_share=float("inf")),
    ],
)
def test_invalid_effective_adjustment_blocks_formal_macd(action: CorporateAction) -> None:
    timestamp = pd.Timestamp("2026-07-13 15:00:00")
    frame = pd.DataFrame({"timestamp": [timestamp], "close": [10.1], "bar_final": [True]})

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=timestamp,
        corporate_actions=(action,),
        expected_bar_times=(timestamp,),
    )

    assert prepared.data_reason is MACDDataReason.PRICE_ADJUSTMENT_UNAVAILABLE
    assert prepared.adjusted_closes == ()


def test_invalid_raw_close_preserves_invalid_close_reason() -> None:
    timestamp = pd.Timestamp("2026-07-13 15:00:00")
    frame = pd.DataFrame({"timestamp": [timestamp], "close": [None], "bar_final": [True]})

    prepared = prepare(
        frame,
        config=MACDConfig(bar_interval=BarInterval.DAY_1),
        evaluation_time=timestamp,
        expected_bar_times=(timestamp,),
    )
    result = calculate_macd_from_bars(prepared, MACDConfig(bar_interval=BarInterval.DAY_1))

    assert prepared.data_reason is MACDDataReason.INVALID_CLOSE
    assert result.data_reason is MACDDataReason.INVALID_CLOSE
    assert result.dif is None


def test_calculation_records_last_closed_bar_time_without_same_bar_lookahead() -> None:
    times = tuple(pd.date_range("2026-06-10 15:00:00", periods=35, freq="D"))
    frame = pd.DataFrame(
        {
            "timestamp": (*times, pd.Timestamp("2026-07-15 15:00:00")),
            "close": tuple(10.0 + index * 0.1 for index in range(35)) + (99.0,),
            "bar_final": (True,) * 35 + (False,),
        }
    )
    config = MACDConfig(bar_interval=BarInterval.DAY_1)

    prepared = prepare(
        frame,
        config=config,
        evaluation_time=times[-1],
        expected_bar_times=times,
    )
    result = calculate_macd_from_bars(prepared, config)

    assert result.data_ready is True
    assert result.provisional is False
    assert result.last_closed_bar_time == str(times[-1])
    assert prepared.provisional_excluded_count == 1


def test_prepare_rejects_config_mismatch_at_calculation_boundary() -> None:
    timestamp = pd.Timestamp("2026-07-13 15:00:00")
    daily = MACDConfig(bar_interval=BarInterval.DAY_1)
    prepared = prepare(
        pd.DataFrame({"timestamp": [timestamp], "close": [10.0], "bar_final": [True]}),
        config=daily,
        evaluation_time=timestamp,
        expected_bar_times=(timestamp,),
    )

    with pytest.raises(MACDBarContractError, match="same MACDConfig"):
        calculate_macd_from_bars(prepared, MACDConfig(bar_interval=BarInterval.MINUTE_5))
