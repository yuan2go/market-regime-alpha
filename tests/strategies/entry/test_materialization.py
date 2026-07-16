from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates import CandidatePopulation
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.time import (
    AsOfTime,
    AvailabilityTime,
    DecisionTime,
    FinalizationTime,
)
from market_regime_alpha.data import (
    RehearsalDecisionSnapshot,
    RehearsalFutureDailyBar,
    RehearsalFutureSuspensionEvidence,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.strategies.entry import (
    EntryBarrierSpec,
    EntryPathObservationStatus,
    EntryPathOutcome,
    EntryPathTriggerType,
    build_entry_path_target_contract,
    materialize_entry_path_target,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_DATE = date(2026, 7, 15)
HORIZON_DATES = (date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22))
PRICE_BASIS = "RAW_UNADJUSTED_TRADABLE_PRICE_V1"
SYMBOL = "000001.SZ"


def _session(value: date) -> TradingSession:
    return TradingSession(
        trade_date=value,
        session_close=datetime(value.year, value.month, value.day, 15, 0, tzinfo=TZ),
    )


def _calendar(*, version: str = "fixture-v1", covered: int = 5):
    dates = (DECISION_DATE, *HORIZON_DATES, date(2026, 7, 23))[:covered]
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version=version,
        timezone_name="Asia/Shanghai",
        sessions=tuple(_session(value) for value in dates),
    )


def _decision_time(*, minute: int = 55) -> DecisionTime:
    return DecisionTime(datetime(2026, 7, 15, 14, minute, tzinfo=TZ))


def _population(
    symbols: tuple[str, ...] = (SYMBOL,),
    *,
    decision_time: DecisionTime | None = None,
) -> CandidatePopulation:
    return CandidatePopulation(
        universe_id=UniverseId("universe-entry-path-v1"),
        decision_time=decision_time or _decision_time(),
        symbols=symbols,
        source_dataset_ids=(DatasetId("dataset-population-v1"),),
    )


def _snapshot(
    symbol: str = SYMBOL,
    *,
    decision_time: DecisionTime | None = None,
) -> RehearsalDecisionSnapshot:
    resolved = decision_time or _decision_time()
    return RehearsalDecisionSnapshot(
        symbol=symbol,
        decision_time=resolved,
        reference_price=10.0,
        available_at=AvailabilityTime(resolved.value),
    )


def _bar(
    session_date: date,
    *,
    symbol: str = SYMBOL,
    open_price: float = 10.0,
    high: float = 10.1,
    low: float = 9.9,
    close: float = 10.0,
    available_minute: int = 5,
    finalized_minute: int = 1,
    price_basis: str = PRICE_BASIS,
) -> RehearsalFutureDailyBar:
    return RehearsalFutureDailyBar(
        symbol=symbol,
        session_date=session_date,
        open=open_price,
        high=high,
        low=low,
        close=close,
        price_adjustment_basis=price_basis,
        available_at=AvailabilityTime(
            datetime(
                session_date.year,
                session_date.month,
                session_date.day,
                15,
                available_minute,
                tzinfo=TZ,
            )
        ),
        finalized_at=FinalizationTime(
            datetime(
                session_date.year,
                session_date.month,
                session_date.day,
                15 if finalized_minute >= 0 else 14,
                finalized_minute if finalized_minute >= 0 else 59,
                tzinfo=TZ,
            )
        ),
    )


def _suspension(
    session_date: date,
    *,
    symbol: str = SYMBOL,
    is_suspended: bool = True,
    available_minute: int = 6,
) -> RehearsalFutureSuspensionEvidence:
    return RehearsalFutureSuspensionEvidence(
        symbol=symbol,
        session_date=session_date,
        is_suspended=is_suspended,
        available_at=AvailabilityTime(
            datetime(
                session_date.year,
                session_date.month,
                session_date.day,
                15,
                available_minute,
                tzinfo=TZ,
            )
        ),
        finalized_at=FinalizationTime(
            datetime(
                session_date.year,
                session_date.month,
                session_date.day,
                15,
                1,
                tzinfo=TZ,
            )
        ),
    )


def _contract(*, horizon_sessions: int = 3):
    return build_entry_path_target_contract(
        EntryBarrierSpec(
            upper_return=0.02,
            lower_return=-0.02,
            horizon_sessions=horizon_sessions,
            price_adjustment_basis=PRICE_BASIS,
        )
    )


def _materialized_at(
    value: datetime = datetime(2026, 7, 22, 15, 10, tzinfo=TZ),
) -> AsOfTime:
    return AsOfTime(value)


def _materialize(
    *,
    bars: tuple[RehearsalFutureDailyBar, ...] = (),
    snapshots: tuple[RehearsalDecisionSnapshot, ...] | None = None,
    suspensions: tuple[RehearsalFutureSuspensionEvidence, ...] = (),
    population: CandidatePopulation | None = None,
    contract=None,
    calendar=None,
    materialized_at: AsOfTime | None = None,
    source_dataset_ids: tuple[DatasetId, ...] = (
        DatasetId("dataset-future-bars-v1"),
        DatasetId("dataset-snapshots-v1"),
    ),
    code_revision: str = "abc123",
    config_hash: str = "sha256:entry-config",
):
    resolved_population = population or _population()
    return materialize_entry_path_target(
        contract=contract or _contract(),
        population=resolved_population,
        source_dataset_ids=source_dataset_ids,
        trading_calendar=calendar or _calendar(),
        decision_snapshots=(
            snapshots
            if snapshots is not None
            else (_snapshot(decision_time=resolved_population.decision_time),)
        ),
        future_daily_bars=bars,
        future_suspensions=suspensions,
        materialized_at=materialized_at or _materialized_at(),
        code_revision=code_revision,
        config_hash=config_hash,
    )


@pytest.mark.parametrize(
    ("bar", "outcome", "trigger"),
    (
        (
            _bar(HORIZON_DATES[0], open_price=10.3, high=10.4, low=10.1, close=10.2),
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.OPEN_GAP_UP,
        ),
        (
            _bar(HORIZON_DATES[0], open_price=9.7, high=9.9, low=9.6, close=9.8),
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.OPEN_GAP_DOWN,
        ),
        (
            _bar(HORIZON_DATES[0], high=10.2, low=9.9, close=10.1),
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.INTRADAY_HIGH_ONLY,
        ),
        (
            _bar(HORIZON_DATES[0], high=10.1, low=9.8, close=9.9),
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.INTRADAY_LOW_ONLY,
        ),
    ),
)
def test_materializer_resolves_first_daily_barrier_event(
    bar: RehearsalFutureDailyBar,
    outcome: EntryPathOutcome,
    trigger: EntryPathTriggerType,
) -> None:
    observation = _materialize(bars=(bar,)).observations[0]

    assert observation.status is EntryPathObservationStatus.AVAILABLE
    assert observation.outcome is outcome
    assert observation.trigger_type is trigger
    assert observation.event_session_date == HORIZON_DATES[0]
    assert observation.event_session_index == 1
    assert observation.evaluated_session_dates == (HORIZON_DATES[0],)
    assert observation.observed_at == bar.available_at
    assert observation.observed_at != AvailabilityTime(bar.finalized_at.value)


def test_dual_touch_is_terminal_ambiguity_even_when_later_bar_is_one_sided() -> None:
    dual = _bar(HORIZON_DATES[0], high=10.2, low=9.8)
    later_up = _bar(HORIZON_DATES[1], high=10.3, low=9.9, close=10.2)

    observation = _materialize(bars=(dual, later_up)).observations[0]

    assert observation.status is EntryPathObservationStatus.AMBIGUOUS
    assert observation.outcome is None
    assert observation.trigger_type is EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED
    assert observation.event_session_date == HORIZON_DATES[0]
    assert observation.evaluated_session_dates == (HORIZON_DATES[0],)
    assert observation.reason_code == "DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED"


def test_complete_untouched_horizon_times_out_at_last_evidence_availability() -> None:
    bars = tuple(
        _bar(value, available_minute=5 + index)
        for index, value in enumerate(HORIZON_DATES)
    )

    observation = _materialize(bars=bars).observations[0]

    assert observation.status is EntryPathObservationStatus.AVAILABLE
    assert observation.outcome is EntryPathOutcome.TIMEOUT
    assert observation.trigger_type is EntryPathTriggerType.HORIZON_EXHAUSTED
    assert observation.event_session_date == HORIZON_DATES[-1]
    assert observation.event_session_index == 3
    assert observation.evaluated_session_dates == HORIZON_DATES
    assert observation.observed_at == bars[-1].available_at


def test_missing_before_event_stops_without_reading_later_bar() -> None:
    later_up = _bar(HORIZON_DATES[1], high=10.3, low=9.9, close=10.2)

    observation = _materialize(bars=(later_up,)).observations[0]

    assert observation.status is EntryPathObservationStatus.MISSING
    assert observation.outcome is None
    assert observation.evaluated_session_dates == ()
    assert observation.first_missing_session_date == HORIZON_DATES[0]
    assert observation.event_session_date is None
    assert observation.observed_at == AvailabilityTime(_materialized_at().value)


def test_missing_after_resolved_event_does_not_change_outcome() -> None:
    first_up = _bar(HORIZON_DATES[0], high=10.3, low=9.9, close=10.2)

    observation = _materialize(bars=(first_up,)).observations[0]

    assert observation.outcome is EntryPathOutcome.UP_FIRST
    assert observation.first_missing_session_date is None


def test_unclosed_unresolved_session_is_not_yet_observed() -> None:
    first = _bar(HORIZON_DATES[0])
    materialized_at = _materialized_at(
        datetime(2026, 7, 21, 14, 0, tzinfo=TZ)
    )

    observation = _materialize(
        bars=(first,),
        materialized_at=materialized_at,
    ).observations[0]

    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.outcome is None
    assert observation.evaluated_session_dates == (HORIZON_DATES[0],)
    assert observation.observed_at is None
    assert observation.reason_code == "HORIZON_NOT_COMPLETE"


def test_missing_snapshot_is_invalid_without_manufacturing_prices() -> None:
    observation = _materialize(snapshots=()).observations[0]

    assert observation.status is EntryPathObservationStatus.INVALID
    assert observation.outcome is None
    assert observation.reference_price is None
    assert observation.upper_price is None
    assert observation.lower_price is None
    assert observation.reason_code == "DECISION_SNAPSHOT_MISSING"
    assert observation.observed_at == AvailabilityTime(_materialized_at().value)


def test_confirmed_suspension_is_evaluated_without_silently_extending_horizon() -> None:
    second_up = _bar(HORIZON_DATES[1], high=10.3, low=9.9, close=10.2)

    observation = _materialize(
        bars=(second_up,),
        suspensions=(_suspension(HORIZON_DATES[0]),),
    ).observations[0]

    assert observation.outcome is EntryPathOutcome.UP_FIRST
    assert observation.event_session_index == 2
    assert observation.evaluated_session_dates == HORIZON_DATES[:2]
    assert observation.observed_at == second_up.available_at


def test_missing_bar_with_non_suspension_evidence_remains_missing() -> None:
    observation = _materialize(
        suspensions=(_suspension(HORIZON_DATES[0], is_suspended=False),),
    ).observations[0]

    assert observation.status is EntryPathObservationStatus.MISSING
    assert observation.first_missing_session_date == HORIZON_DATES[0]


def test_empty_population_produces_identified_empty_materialization() -> None:
    result = _materialize(
        population=_population(()),
        snapshots=(),
    )

    assert result.observations == ()
    assert str(result.artifact_id).startswith("entry-path-materialization-")


@pytest.mark.parametrize(
    "case",
    ("snapshots", "bars", "suspensions"),
)
def test_duplicate_evidence_fails_entire_materialization(case: str) -> None:
    snapshot = _snapshot()
    bar = _bar(HORIZON_DATES[0])
    suspension = _suspension(HORIZON_DATES[0])
    arguments = {
        "snapshots": (snapshot,),
        "bars": (bar,),
        "suspensions": (),
    }
    arguments[case] = {
        "snapshots": (snapshot, snapshot),
        "bars": (bar, bar),
        "suspensions": (suspension, suspension),
    }[case]

    with pytest.raises(ValueError, match="duplicate"):
        _materialize(**arguments)  # type: ignore[arg-type]


def test_wrong_decision_time_fails_entire_materialization() -> None:
    wrong_time = _decision_time(minute=54)
    population = _population(decision_time=wrong_time)

    with pytest.raises(ValueError, match="14:55:00 Asia/Shanghai"):
        _materialize(
            population=population,
            snapshots=(_snapshot(decision_time=wrong_time),),
        )


def test_off_calendar_and_outside_horizon_evidence_fail_closed() -> None:
    with pytest.raises(ValueError, match="off-Calendar"):
        _materialize(bars=(_bar(date(2026, 7, 19)),))

    with pytest.raises(ValueError, match="outside resolved Target horizon"):
        _materialize(bars=(_bar(date(2026, 7, 23)),))


def test_future_available_and_pre_close_finalization_fail_closed() -> None:
    decision_time = _decision_time()
    with pytest.raises(ValueError, match="available by decision_time"):
        RehearsalDecisionSnapshot(
            symbol=SYMBOL,
            decision_time=decision_time,
            reference_price=10.0,
            available_at=AvailabilityTime(
                datetime(2026, 7, 15, 14, 56, tzinfo=TZ)
            ),
        )

    with pytest.raises(ValueError, match="available after materialized_at"):
        _materialize(
            bars=(_bar(HORIZON_DATES[0], available_minute=10),),
            materialized_at=_materialized_at(
                datetime(2026, 7, 20, 15, 5, tzinfo=TZ)
            ),
        )

    with pytest.raises(ValueError, match="finalized before TradingSession close"):
        _materialize(bars=(_bar(HORIZON_DATES[0], finalized_minute=-1),))


def test_conflicting_suspension_and_price_bar_fail_closed() -> None:
    with pytest.raises(ValueError, match="confirmed suspension conflicts"):
        _materialize(
            bars=(_bar(HORIZON_DATES[0]),),
            suspensions=(_suspension(HORIZON_DATES[0]),),
        )


def test_adjustment_basis_and_source_identity_mismatches_fail_closed() -> None:
    with pytest.raises(ValueError, match="price adjustment basis"):
        _materialize(
            bars=(_bar(HORIZON_DATES[0], price_basis="FORWARD_ADJUSTED_V1"),)
        )

    duplicate = DatasetId("dataset-duplicate-v1")
    with pytest.raises(ValueError, match="source_dataset_ids must be unique"):
        _materialize(source_dataset_ids=(duplicate, duplicate))


def test_calendar_coverage_failure_is_structural_even_for_empty_population() -> None:
    with pytest.raises(LookupError, match="insufficient later trading sessions"):
        _materialize(
            population=_population(()),
            snapshots=(),
            calendar=_calendar(covered=3),
        )


def test_artifact_identity_is_input_order_invariant_and_semantically_sensitive() -> None:
    symbols = ("000001.SZ", "000002.SZ")
    population = _population(symbols)
    snapshots = tuple(_snapshot(symbol) for symbol in symbols)
    bars = tuple(
        _bar(
            HORIZON_DATES[0],
            symbol=symbol,
            open_price=10.3,
            high=10.4,
            low=10.1,
            close=10.2,
        )
        for symbol in symbols
    )

    first = _materialize(population=population, snapshots=snapshots, bars=bars)
    reordered = _materialize(
        population=population,
        snapshots=tuple(reversed(snapshots)),
        bars=tuple(reversed(bars)),
    )
    changed_config = _materialize(
        population=population,
        snapshots=snapshots,
        bars=bars,
        config_hash="sha256:changed",
    )
    changed_calendar = _materialize(
        population=population,
        snapshots=snapshots,
        bars=bars,
        calendar=_calendar(version="fixture-v2"),
    )

    assert first.artifact_id == reordered.artifact_id
    assert first.artifact_id != changed_config.artifact_id
    assert first.artifact_id != changed_calendar.artifact_id
    assert first.target_id == _contract().target_id
