from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from market_regime_alpha.application.research_validation.free_historical_samples import (
    FreeHistoricalBar,
    FreeHistoricalSamplePipeline,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalSampleDataset,
    HistoricalSampleQualification,
)
from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_CONFIG_SCHEMA,
    PathForecastConfig,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryBarrierSpec,
    build_entry_path_target_contract,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")


class _Reader:
    provider_id = "BAOSTOCK_5MIN_TEST"
    price_adjustment_basis = "RAW_UNADJUSTED_TRADABLE_PRICE_V1"

    def __init__(self, bars: dict[str, tuple[FreeHistoricalBar, ...]]) -> None:
        self._bars = bars

    def read(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[FreeHistoricalBar, ...]:
        del start_date, end_date
        if symbol == "000002.SZ":
            raise RuntimeError("provider unavailable")
        return self._bars.get(symbol, ())


class _Writer:
    def __init__(self) -> None:
        self.datasets: list[HistoricalSampleDataset] = []
        self.decisions = []
        self.outcomes = []

    def record_sample_dataset(self, dataset: HistoricalSampleDataset) -> None:
        self.datasets.append(dataset)

    def record_free_historical_pipeline(
        self,
        *,
        decisions,
        outcomes,
        dataset: HistoricalSampleDataset,
    ) -> None:
        self.decisions.extend(decisions)
        self.outcomes.extend(outcomes)
        self.record_sample_dataset(dataset)

    def find_sample_dataset(
        self,
        *,
        registry_version: str,
        target_id: object,
    ) -> HistoricalSampleDataset | None:
        return next(
            (
                item
                for item in reversed(self.datasets)
                if item.registry_version == registry_version
                and str(item.target_reference.artifact_id) == str(target_id)
            ),
            None,
        )


def test_builds_unqualified_multi_horizon_registry_samples() -> None:
    retrieved_at = datetime(2026, 8, 10, 6, 54, tzinfo=UTC)
    writer = _Writer()
    pipeline = FreeHistoricalSamplePipeline(
        reader=_Reader({"000001.SZ": _bars("000001.SZ", date(2026, 7, 20), 8)}),
        repository=writer,
        clock=lambda: retrieved_at,
        maximum_samples_per_symbol=3,
    )

    result = pipeline.build_and_register(
        symbols=("000001.SZ", "000002.SZ"),
        configuration=_configuration(),
        current_decision_time=DecisionTime(datetime(2026, 8, 10, 14, 55, tzinfo=_SHANGHAI)),
    )

    assert result.dataset is not None
    assert result.sample_count == 3
    assert result.dataset.qualification is HistoricalSampleQualification.UNQUALIFIED
    assert result.provider_failures == (("000002.SZ", "RuntimeError"),)
    assert result.dataset.available_at == retrieved_at
    assert all(record.qualification is HistoricalSampleQualification.UNQUALIFIED for record in result.dataset.records)
    assert all("FREE_DATA_EXPLORATORY" in record.reason_codes for record in result.dataset.records)
    assert all(record.sample.available_at.value == retrieved_at for record in result.dataset.records)
    assert all(record.outcome_reference.artifact_kind == "FREE_HISTORICAL_MULTI_HORIZON_OUTCOME" for record in result.dataset.records)
    assert all(outcome.checkpoint_prices[0][0] == "09:45" for outcome in result.outcomes)
    assert {name for name, _ in result.outcomes[0].checkpoint_prices} == {
        "OPEN",
        "09:45",
        "10:00",
        "10:30",
        "11:30",
        "CLOSE",
    }
    assert writer.datasets == [result.dataset]
    assert writer.decisions == list(result.decisions)
    assert writer.outcomes == list(result.outcomes)

    replayed = pipeline.build_and_register(
        symbols=("000001.SZ", "000002.SZ"),
        configuration=_configuration(),
        current_decision_time=DecisionTime(datetime(2026, 8, 10, 14, 55, tzinfo=_SHANGHAI)),
    )
    # The failed symbol remains retryable; the successful symbol is replaced,
    # not duplicated, in the new cumulative immutable dataset.
    assert replayed.sample_count == 3
    assert len({(item.sample.symbol, item.sample.sample_decision_time.value) for item in replayed.dataset.records}) == 3  # type: ignore[union-attr]


def test_missing_exact_1455_reference_does_not_fabricate_sample() -> None:
    bars = tuple(
        bar
        for bar in _bars("000001.SZ", date(2026, 7, 20), 5)
        if bar.observed_at.time() != time(14, 55)
    )
    result = FreeHistoricalSamplePipeline(
        reader=_Reader({"000001.SZ": bars}),
        repository=_Writer(),
        clock=lambda: datetime(2026, 8, 10, 6, 54, tzinfo=UTC),
    ).build_and_register(
        symbols=("000001.SZ",),
        configuration=_configuration(),
        current_decision_time=DecisionTime(datetime(2026, 8, 10, 14, 55, tzinfo=_SHANGHAI)),
    )

    assert result.dataset is None
    assert result.sample_count == 0
    assert result.skipped_symbols == ("000001.SZ",)


def test_rejects_target_adjustment_semantics_that_the_reader_does_not_own() -> None:
    configuration = _configuration(price_adjustment_basis="FORWARD_ADJUSTED")
    pipeline = FreeHistoricalSamplePipeline(
        reader=_Reader({"000001.SZ": _bars("000001.SZ", date(2026, 7, 20), 5)}),
        repository=_Writer(),
        clock=lambda: datetime(2026, 8, 10, 6, 54, tzinfo=UTC),
    )

    try:
        pipeline.build_and_register(
            symbols=("000001.SZ",),
            configuration=configuration,
            current_decision_time=DecisionTime(
                datetime(2026, 8, 10, 14, 55, tzinfo=_SHANGHAI)
            ),
        )
    except ValueError as exc:
        assert "price adjustment basis" in str(exc)
    else:
        raise AssertionError("mismatched adjustment basis must fail closed")


def _configuration(
    *,
    price_adjustment_basis: str = "RAW_UNADJUSTED_TRADABLE_PRICE_V1",
) -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="free-historical-test-v1",
        model_id=ModelId("free-historical-path-model-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-1455-v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=build_entry_path_target_contract(
            EntryBarrierSpec(
                upper_return=0.03,
                lower_return=-0.02,
                horizon_sessions=2,
                price_adjustment_basis=price_adjustment_basis,
            )
        ),
        horizon_label="2_TRADING_SESSIONS",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=2,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _bars(symbol: str, start: date, count: int) -> tuple[FreeHistoricalBar, ...]:
    values = []
    session = start
    sessions = 0
    while sessions < count:
        if session.weekday() >= 5:
            session += timedelta(days=1)
            continue
        base = Decimal("10") + Decimal(sessions) / Decimal("10")
        for observed_time in (
            time(9, 35),
            time(9, 45),
            time(10, 0),
            time(10, 30),
            time(11, 30),
            time(14, 55),
            time(15, 0),
        ):
            values.append(
                FreeHistoricalBar(
                    symbol=symbol,
                    observed_at=datetime.combine(session, observed_time, tzinfo=_SHANGHAI),
                    open=base,
                    high=base + Decimal("0.20"),
                    low=base - Decimal("0.10"),
                    close=base + Decimal("0.05"),
                )
            )
        sessions += 1
        session += timedelta(days=1)
    return tuple(values)
