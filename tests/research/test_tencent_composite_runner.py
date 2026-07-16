from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features.rehearsal_baselines import (
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
    build_tencent_composite_dataset_contract,
)
from market_regime_alpha.research.tencent_composite_runner import (
    r5_b1_exploratory_specs,
    run_tencent_composite_candidate_experiment,
)


TZ = ZoneInfo("Asia/Shanghai")


def _prepared_data(
    *,
    session_count: int = 82,
    symbol_count: int = 16,
) -> PreparedCompositeData:
    symbols = tuple(f"{index + 1:06d}.SZ" for index in range(symbol_count))
    dates = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(session_count))
    sessions = tuple(
        PreparedCompositeSession(
            symbol=symbol,
            session_date=session_date,
            open=100.0 + date_index + symbol_index / 10,
            high=102.0 + date_index + symbol_index / 10,
            low=99.0 + date_index + symbol_index / 10,
            close=101.0 + date_index + symbol_index / 10,
            amount=1_000_000.0 + date_index * 1_000 + symbol_index,
            reference_price=101.5 + date_index + symbol_index / 10,
            reference_timestamp=datetime.combine(
                session_date,
                datetime.min.time(),
                tzinfo=TZ,
            ).replace(hour=14, minute=50),
            source_kinds=(CompositeSourceKind.LOCAL,),
        )
        for date_index, session_date in enumerate(dates)
        for symbol_index, symbol in enumerate(symbols)
    )
    dispositions = tuple(
        CompositeSymbolDisposition(
            symbol=symbol,
            code=CompositeDispositionCode.ACCEPTED,
            complete_session_count=session_count,
            findings=(),
        )
        for symbol in symbols
    )
    quality = CompositeQualityReport(
        requested_symbols=symbols,
        accepted_symbols=symbols,
        dispositions=dispositions,
        common_session_dates=dates,
        required_session_count=82,
        minimum_accepted_symbols=16,
    )
    return PreparedCompositeData(
        accepted_symbols=symbols,
        common_session_dates=dates,
        sessions=sessions,
        quality=quality,
        limitations=("CURRENT_WATCHLIST_BACKFILL_BIAS",),
    )


def _exploratory_contract():
    return build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:local", "sha256:tencent"),
        code_revision="abc123",
        config_hash="sha256:config",
    )


def test_b1_ladder_matches_declared_ablation_family() -> None:
    specs = r5_b1_exploratory_specs()

    assert tuple(specs) == ("B1-A", "B1-B", "B1-C", "B1-D", "B1-E")
    assert tuple(component.feature_id for component in specs["B1-A"].components) == (
        MOMENTUM_5S_ID,
    )
    assert PRICE_VS_MA20_ID not in {
        component.feature_id for component in specs["B1-D"].components
    }
    assert PRICE_VS_MA20_ID in {
        component.feature_id for component in specs["B1-E"].components
    }


def test_candidate_run_evaluates_sixty_dates_for_all_three_targets() -> None:
    result = run_tencent_composite_candidate_experiment(
        prepared=_prepared_data(),
        dataset_contract=_exploratory_contract(),
        retrieved_at=RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ)),
        code_revision="abc123",
        config_hash="sha256:config",
    )

    assert result.decision_date_count == 60
    assert len(result.target_runs) == 3
    assert all(target.panel.slice_count == 60 for target in result.target_runs)
    assert all(len(target.b0_evaluations) == 4 for target in result.target_runs)
    assert all(len(target.b1_evaluations) == 5 for target in result.target_runs)
    assert all(
        evaluation.evaluation.slice_count == 60
        for target in result.target_runs
        for evaluation in (*target.b0_evaluations, *target.b1_evaluations)
    )
    assert result.data_eligibility is DataEligibility.EXPLORATORY
