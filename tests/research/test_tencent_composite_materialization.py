from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MAE_TARGET_ID,
    R5_NEXT_SESSION_MFE_TARGET_ID,
)
from market_regime_alpha.candidates.rehearsal_targets import R5_NEXT_SESSION_RETURN_TARGET_ID
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features.rehearsal_baselines import MOMENTUM_5S_ID
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
    build_tencent_composite_dataset_contract,
)
from market_regime_alpha.research.tencent_composite_materialization import (
    materialize_tencent_composite_slice,
)


TZ = ZoneInfo("Asia/Shanghai")


def _prepared_data() -> PreparedCompositeData:
    symbols = ("000001.SZ", "000002.SZ")
    dates = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(23))
    sessions = tuple(
        PreparedCompositeSession(
            symbol=symbol,
            session_date=session_date,
            open=100.0 + index + symbol_index,
            high=102.0 + index + symbol_index,
            low=99.0 + index + symbol_index,
            close=101.0 + index + symbol_index,
            amount=1_000_000.0 + index,
            reference_price=101.5 + index + symbol_index,
            reference_timestamp=datetime.combine(
                session_date,
                datetime.min.time(),
                tzinfo=TZ,
            ).replace(hour=14, minute=50),
            source_kinds=(CompositeSourceKind.LOCAL,),
        )
        for index, session_date in enumerate(dates)
        for symbol_index, symbol in enumerate(symbols)
    )
    dispositions = tuple(
        CompositeSymbolDisposition(
            symbol=symbol,
            code=CompositeDispositionCode.ACCEPTED,
            complete_session_count=23,
            findings=(),
        )
        for symbol in symbols
    )
    quality = CompositeQualityReport(
        requested_symbols=symbols,
        accepted_symbols=symbols,
        dispositions=dispositions,
        common_session_dates=dates,
        required_session_count=23,
        minimum_accepted_symbols=2,
    )
    return PreparedCompositeData(
        accepted_symbols=symbols,
        common_session_dates=dates,
        sessions=sessions,
        quality=quality,
        limitations=("CURRENT_WATCHLIST_BACKFILL_BIAS",),
    )


def _contract():
    return build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:local", "sha256:tencent"),
        code_revision="abc123",
        config_hash="sha256:config",
    )


def test_materialized_slices_are_exploratory_and_use_retrieval_time_for_targets() -> None:
    prepared = _prepared_data()
    decision_date = prepared.common_session_dates[-2]
    retrieved_at = RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ))

    datasets = materialize_tencent_composite_slice(
        prepared=prepared,
        decision_date=decision_date,
        dataset_contract=_contract(),
        retrieved_at=retrieved_at,
        code_revision="abc123",
        config_hash="sha256:config",
    )

    assert len(datasets) == 3
    assert {dataset.target_id for dataset in datasets} == {
        R5_NEXT_SESSION_RETURN_TARGET_ID,
        R5_NEXT_SESSION_MFE_TARGET_ID,
        R5_NEXT_SESSION_MAE_TARGET_ID,
    }
    assert all(dataset.data_eligibility is DataEligibility.EXPLORATORY for dataset in datasets)
    assert all(
        row.target.observed_at is not None
        and row.target.observed_at.value == retrieved_at.value
        for dataset in datasets
        for row in dataset.rows
    )
    assert all("CURRENT_WATCHLIST_BACKFILL_BIAS" in dataset.limitations for dataset in datasets)


def test_materializer_uses_prior_sessions_and_current_reference_without_future_features() -> None:
    prepared = _prepared_data()
    decision_date = prepared.common_session_dates[-2]
    datasets = materialize_tencent_composite_slice(
        prepared=prepared,
        decision_date=decision_date,
        dataset_contract=_contract(),
        retrieved_at=RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ)),
        code_revision="abc123",
        config_hash="sha256:config",
    )
    row = datasets[0].rows[0]
    feature_values = {item.feature_id: item.value for item in row.feature_values}
    decision_session = prepared.session_for(row.symbol, decision_date)
    prior_fifth = prepared.session_for(row.symbol, prepared.common_session_dates[-7])

    assert feature_values[MOMENTUM_5S_ID] == pytest.approx(
        decision_session.reference_price / prior_fifth.close - 1.0
    )


def test_materializer_rejects_stronger_or_pit_dataset_authority() -> None:
    prepared = _prepared_data()
    contract = _contract()
    decision_date = prepared.common_session_dates[-2]
    retrieved_at = RetrievedAt(datetime(2026, 7, 16, 16, 0, tzinfo=TZ))

    for invalid in (
        replace(contract, eligibility=DataEligibility.REHEARSAL),
        replace(contract, pit_correct_for_scope=True),
    ):
        with pytest.raises(ValueError, match="non-PIT EXPLORATORY"):
            materialize_tencent_composite_slice(
                prepared=prepared,
                decision_date=decision_date,
                dataset_contract=invalid,
                retrieved_at=retrieved_at,
                code_revision="abc123",
                config_hash="sha256:config",
            )
