from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessConclusion,
    AlphaCorrectnessStatus,
    PersistedFeatureObservation,
    PersistedTargetObservation,
    _physical_verification_from_reloaded_packages,
    build_alpha_correctness_proof,
    reproduce_execution_timing_diagnostics,
    reproduce_intraday_features,
    reproduce_t_plus_one_1030_target,
)
from market_regime_alpha.application.historical_corpus.alpha_diagnostics import (
    AlphaObservation,
    ExecutionPriceInputs,
    ExecutionPriceProxy,
    FactorObservation,
    FrozenPlaceboProtocol,
    MovingBlockInferenceProtocol,
    PlaceboKind,
    SessionEstimate,
    TimedPriceObservation,
    apply_placebo,
    diagnose_execution_price,
    evaluate_factor_redundancy,
    evaluate_robust_inference_family,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    load_verified_historical_package,
    publish_historical_package,
)
from market_regime_alpha.application.historical_corpus.raw_normalization_correctness import (
    IndependentNormalizationStatus,
    IndependentNormalizationVerification,
    PhysicalAcquisitionProvenance,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe


SHANGHAI = ZoneInfo("Asia/Shanghai")
SESSION = date(2025, 1, 2)
NEXT_SESSION = date(2025, 1, 3)
DECISION_TIME = datetime.combine(SESSION, time(14, 55), SHANGHAI).astimezone(UTC)


def test_independent_intraday_recomputation_matches_persisted_values(tmp_path) -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = tuple(
        PersistedFeatureObservation.create(
            factor_id=factor_id,
            value=value,
            source_bars=bars,
        )
        for factor_id, value in (
            ("intraday_return_to_decision_time", Decimal("0.200000000000")),
            ("price_vs_vwap_return", Decimal("0.090909090909")),
            ("vwap_slope", Decimal("0.100000000000")),
        )
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_verification=_physical_verification(tmp_path, bars),
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert result.discrepancies == ()
    assert {item.factor_id: item.recomputed_value for item in result.comparisons} == {
        "intraday_return_to_decision_time": Decimal("0.200000000000"),
        "price_vs_vwap_return": Decimal("0.090909090909"),
        "vwap_slope": Decimal("0.100000000000"),
    }
    assert all(item.event_end <= DECISION_TIME for item in result.comparisons)


def test_intraday_recomputation_mismatch_fails_closed(tmp_path) -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = (
        PersistedFeatureObservation.create(
            factor_id="intraday_return_to_decision_time",
            value=Decimal("0.199999999999"),
            source_bars=bars,
        ),
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_verification=_physical_verification(tmp_path, bars),
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_FAILED
    assert result.discrepancies == (
        "VALUE_MISMATCH:intraday_return_to_decision_time",
    )


def test_owner_replay_cannot_claim_physical_reproduction() -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = (
        PersistedFeatureObservation.create(
            factor_id="intraday_return_to_decision_time",
            value=Decimal("0.200000000000"),
            source_bars=bars,
        ),
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_verification=None,
    )

    assert (
        result.status
        is AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    )
    assert result.discrepancies == ()


def test_t_plus_one_target_is_recomputed_from_a_later_session_checkpoint(tmp_path) -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )
    target_bars = tuple(
        _bar(
            NEXT_SESSION,
            (datetime.combine(NEXT_SESSION, time(9, 30)) + timedelta(minutes=5 * index)).time(),
            open_price=str(Decimal("12") + Decimal(index) / Decimal("10")),
            close=str(Decimal("12.1") + Decimal(index) / Decimal("10")),
            volume="100",
            row=100 + index,
        )
        for index in range(12)
    )
    persisted = PersistedTargetObservation.create(
        decision_reference_price=Decimal("12"),
        target_price=Decimal("13.2"),
        target_return=Decimal("0.1"),
        decision_source_bars=(decision_bar,),
        target_source_bars=target_bars,
        target_session=NEXT_SESSION,
    )

    result = reproduce_t_plus_one_1030_target(
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        next_session=NEXT_SESSION,
        trading_calendar=_calendar(),
        source_bars=(decision_bar, *target_bars),
        persisted=persisted,
        physical_verification=_physical_verification(
            tmp_path, (decision_bar, *target_bars)
        ),
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert result.decision_reference_price == Decimal("12")
    assert result.target_price == Decimal("13.2")
    assert result.target_return == Decimal("0.1")
    assert result.target_session > SESSION
    assert result.target_event_end == datetime.combine(
        NEXT_SESSION, time(10, 30), SHANGHAI
    ).astimezone(UTC)
    assert set(result.decision_source_ids).isdisjoint(result.target_source_ids)


def test_execution_proxies_are_selected_by_frozen_bar_semantics(tmp_path) -> None:
    decision = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )
    session_close = _bar(
        SESSION,
        time(14, 55),
        open_price="12.05",
        close="12.1",
        volume="100",
        row=2,
    )
    target_bars = tuple(
        _bar(
            NEXT_SESSION,
            (
                datetime.combine(NEXT_SESSION, time(9, 30))
                + timedelta(minutes=5 * index)
            ).time(),
            open_price=("12.2" if index == 0 else "12.3"),
            close=("12.4" if index == 11 else "12.3"),
            volume="100",
            row=100 + index,
        )
        for index in range(12)
    )
    physical = _physical_verification(
        tmp_path,
        (decision, session_close, *target_bars),
    )
    persisted = PersistedTargetObservation.create(
        decision_reference_price=Decimal("12"),
        target_price=Decimal("12.4"),
        target_return=(Decimal("12.4") - Decimal("12")) / Decimal("12"),
        decision_source_bars=(decision,),
        target_source_bars=target_bars,
        target_session=NEXT_SESSION,
    )
    target = reproduce_t_plus_one_1030_target(
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        next_session=NEXT_SESSION,
        trading_calendar=_calendar(),
        source_bars=(decision, session_close, *target_bars),
        persisted=persisted,
        physical_verification=physical,
    )

    by_proxy = {
        item.proxy: item
        for item in reproduce_execution_timing_diagnostics(
            target=target,
            source_bars=(decision, session_close, *target_bars),
        )
    }

    assert by_proxy[ExecutionPriceProxy.NEXT_OBSERVABLE_PRICE].entry_price == Decimal(
        "12.1"
    )
    assert by_proxy[ExecutionPriceProxy.NEXT_BAR_OPEN].entry_price == Decimal(
        "12.2"
    )
    assert by_proxy[ExecutionPriceProxy.SESSION_CLOSE].entry_price == Decimal(
        "12.1"
    )
    assert (
        by_proxy[ExecutionPriceProxy.DECISION_REFERENCE_ONLY].executable is False
    )


def test_correctness_proof_requires_all_factors_target_and_physical_lineage(
    tmp_path,
) -> None:
    decision_bars = (
        _bar(SESSION, time(14, 45), open_price="12", close="12", volume="100"),
        _bar(SESSION, time(14, 50), open_price="12", close="12", volume="100"),
    )
    target_bars = tuple(
        _bar(
            NEXT_SESSION,
            (datetime.combine(NEXT_SESSION, time(9, 30)) + timedelta(minutes=5 * index)).time(),
            open_price="12",
            close="12",
            volume="100",
            row=200 + index,
        )
        for index in range(12)
    )
    persisted_features = tuple(
        PersistedFeatureObservation.create(
            factor_id=factor_id,
            value=Decimal("0E-12"),
            source_bars=decision_bars,
        )
        for factor_id in (
            "intraday_return_to_decision_time",
            "price_vs_vwap_return",
            "vwap_slope",
        )
    )
    persisted_target = PersistedTargetObservation.create(
        decision_reference_price=Decimal("12"),
        target_price=Decimal("12"),
        target_return=Decimal("0"),
        decision_source_bars=(decision_bars[-1],),
        target_source_bars=target_bars,
        target_session=NEXT_SESSION,
    )
    physical = _physical_verification(tmp_path, (*decision_bars, *target_bars))
    normalization = _matched_normalization_verification(physical)
    features = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=decision_bars,
        persisted=persisted_features,
        physical_verification=physical,
    )
    target = reproduce_t_plus_one_1030_target(
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        next_session=NEXT_SESSION,
        trading_calendar=_calendar(),
        source_bars=(*decision_bars, *target_bars),
        persisted=persisted_target,
        physical_verification=physical,
    )

    proof = build_alpha_correctness_proof(
        feature_results=(features,),
        target_results=(target,),
        physical_verifications=(physical,),
        normalization_verifications=(normalization,),
        placebo_results=_complete_placebos(),
        execution_diagnostics=_execution_diagnostics(),
        factor_redundancy=_redundancy(),
        robust_inference=_robust_inference(),
    )

    assert proof.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert proof.conclusion is AlphaCorrectnessConclusion.CORRECTNESS_SUPPORTED
    assert proof.reference.content_hash == proof.proof_hash
    assert "ALPHA_PROVEN_FALSE" in proof.limitations

    incomplete = build_alpha_correctness_proof(
        feature_results=(features,),
        target_results=(target,),
        physical_verifications=(physical,),
        normalization_verifications=(normalization,),
        placebo_results=(),
        execution_diagnostics=_execution_diagnostics(),
        factor_redundancy=_redundancy(),
        robust_inference=_robust_inference(),
    )
    assert incomplete.status is AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    assert incomplete.conclusion is AlphaCorrectnessConclusion.INCONCLUSIVE

    raw_layer_missing = build_alpha_correctness_proof(
        feature_results=(features,),
        target_results=(target,),
        physical_verifications=(physical,),
        placebo_results=_complete_placebos(),
        execution_diagnostics=_execution_diagnostics(),
        factor_redundancy=_redundancy(),
        robust_inference=_robust_inference(),
    )
    assert raw_layer_missing.status is AlphaCorrectnessStatus.PARTIALLY_REPRODUCED
    assert raw_layer_missing.conclusion is AlphaCorrectnessConclusion.INCONCLUSIVE


def _complete_placebos():
    observations = tuple(
        AlphaObservation(
            session,
            symbol,
            Decimal(index + 1),
            Decimal(index + (1 if session == SESSION else 2)) / Decimal("100"),
        )
        for session in (SESSION, NEXT_SESSION)
        for index, symbol in enumerate(("600000.SH", "600001.SH", "600002.SH"))
    )
    return tuple(
        apply_placebo(protocol, kind=kind, observations=observations)
        for factor_id in (
            "intraday_return_to_decision_time",
            "price_vs_vwap_return",
            "vwap_slope",
        )
        for protocol in (
            FrozenPlaceboProtocol.create(
                factor_id=factor_id,
                target_id="t-plus-one-1030",
                seed=7,
                kinds=tuple(PlaceboKind),
            ),
        )
        for kind in PlaceboKind
    )


def _execution_diagnostics():
    target_time = datetime.combine(NEXT_SESSION, time(10, 30), SHANGHAI).astimezone(UTC)
    source = ValidationArtifactReference(
        "NORMALIZED_DATASET",
        ArtifactId("execution-owner"),
        canonical_hash({"execution": "owner"}),
    )

    def observed(minutes: int, price: str) -> TimedPriceObservation:
        at = DECISION_TIME + timedelta(minutes=minutes)
        return TimedPriceObservation(Decimal(price), at, at, source)

    inputs = ExecutionPriceInputs(
        information_cutoff=DECISION_TIME,
        decision_reference=TimedPriceObservation(
            Decimal("12"), DECISION_TIME, DECISION_TIME, source
        ),
        next_observable_price=observed(1, "12.01"),
        next_bar_open=observed(5, "12.02"),
        session_close=observed(10, "12.03"),
        target_reference=TimedPriceObservation(
            Decimal("12.2"), target_time, target_time, source
        ),
    )
    return tuple(diagnose_execution_price(inputs, proxy) for proxy in ExecutionPriceProxy)


def _redundancy():
    factor_values = (
        (1, 2, 5, 1),
        (2, 5, 1, 3),
        (3, 1, 4, 5),
        (4, 4, 2, 2),
        (5, 3, 3, 4),
    )
    observations = tuple(
        FactorObservation(
            session,
            symbol,
            {
                "intraday_return_to_decision_time": Decimal(values[0]),
                "price_vs_vwap_return": Decimal(values[1]),
                "vwap_slope": Decimal(values[2]),
            },
            Decimal(values[3]) / Decimal("100"),
        )
        for session in (SESSION, NEXT_SESSION)
        for symbol, values in zip(
            ("600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"),
            factor_values,
            strict=True,
        )
    )
    return evaluate_factor_redundancy(observations)


def _robust_inference():
    protocol = MovingBlockInferenceProtocol.create(
        iterations=20,
        block_lengths=(1,),
        confidence_level=Decimal("0.9"),
        seed=11,
    )
    observations = tuple(
        SessionEstimate(SESSION + timedelta(days=index), Decimal(index + 1) / Decimal("100"))
        for index in range(4)
    )
    results = evaluate_robust_inference_family(
        protocol,
        {
            factor_id: observations
            for factor_id in (
                "intraday_return_to_decision_time",
                "price_vs_vwap_return",
                "vwap_slope",
            )
        },
    )
    return tuple(sorted(results.items()))


def test_t_plus_one_target_rejects_same_session_and_future_feature_lineage() -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )

    with pytest.raises(ValueError, match="immediate next"):
        reproduce_t_plus_one_1030_target(
            symbol="600000.SH",
            decision_time=DECISION_TIME,
            next_session=SESSION,
            trading_calendar=_calendar(),
            source_bars=(decision_bar,),
            persisted=None,
            physical_verification=None,
        )


def test_t_plus_one_target_requires_complete_open_to_checkpoint_window() -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )
    incomplete = tuple(
        _bar(
            NEXT_SESSION,
            (
                datetime.combine(NEXT_SESSION, time(9, 35))
                + timedelta(minutes=5 * index)
            ).time(),
            open_price="13",
            close="13",
            volume="100",
            row=200 + index,
        )
        for index in range(11)
    )

    with pytest.raises(ValueError, match="checkpoint is incomplete"):
        reproduce_t_plus_one_1030_target(
            symbol="600000.SH",
            decision_time=DECISION_TIME,
            next_session=NEXT_SESSION,
            trading_calendar=_calendar(),
            source_bars=(decision_bar, *incomplete),
            persisted=None,
            physical_verification=None,
        )


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("calendar-source"),
        market="A_SHARE",
        calendar_version="test-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(
                SESSION,
                datetime.combine(SESSION, time(15), SHANGHAI),
            ),
            TradingSession(
                NEXT_SESSION,
                datetime.combine(NEXT_SESSION, time(15), SHANGHAI),
            ),
        ),
    )


def _physical_verification(tmp_path, bars):
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=tuple(bars),
        bucket_count=4,
    )
    sessions = {item.market_date for item in bars}
    owner = HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id="TEST_PHYSICAL",
        normalization_version="correctness-test/v1",
        parent_reference=ValidationArtifactReference(
            "RAW_PROVIDER_ARCHIVE",
            ArtifactId("raw-physical-owner"),
            canonical_hash({"raw": "physical-owner"}),
        ),
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        first_market_date=min(sessions),
        last_market_date=max(sessions),
        bucket_count=4,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=("600000.SH",),
            observed_symbols=("600000.SH",),
            expected_request_count=len(sessions),
            successful_request_count=len(sessions),
            source_row_count=len(bars),
            normalized_row_count=len(bars),
            missing_field_counts=(),
            failure_counts=(),
        ),
        limitations=("PIT_INCOMPLETE",),
    )
    path = publish_historical_package(artifact_root=tmp_path, owner=owner)
    return _physical_verification_from_reloaded_packages(
        physical_package=load_verified_historical_package(path),
        postgres_owner_package=load_verified_historical_package(path),
    )


def _matched_normalization_verification(
    physical,
) -> IndependentNormalizationVerification:
    value_hash = canonical_hash({"test": "independent-normalization"})
    return IndependentNormalizationVerification.create(
        provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
        raw_owner_reference=ValidationArtifactReference(
            "RAW_PROVIDER_ARCHIVE",
            ArtifactId("raw-physical-owner"),
            canonical_hash({"raw": "physical-owner"}),
        ),
        normalized_owner_reference=physical.normalized_owner_reference,
        comparison_count=len(physical.normalized_bar_bindings),
        independent_value_hash=value_hash,
        canonical_value_hash=value_hash,
        status=IndependentNormalizationStatus.MATCHED,
        discrepancies=(),
        reason_codes=("RAW_NORMALIZATION_MATCHED",),
    )


def _bar(
    market_date: date,
    start_time: time,
    *,
    open_price: str,
    close: str,
    volume: str,
    row: int = 1,
) -> HistoricalNormalizedBar:
    event_start = datetime.combine(market_date, start_time, SHANGHAI).astimezone(UTC)
    close_value = Decimal(close)
    volume_value = Decimal(volume)
    return HistoricalNormalizedBar.create(
        symbol="600000.SH",
        timeframe=Timeframe.MINUTE_5,
        market_date=market_date,
        event_start=event_start,
        event_end=event_start + timedelta(minutes=5),
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        open=Decimal(open_price),
        high=max(Decimal(open_price), close_value),
        low=min(Decimal(open_price), close_value),
        close=close_value,
        volume=volume_value,
        amount=volume_value * close_value,
        adjustment_basis="RAW_UNADJUSTED",
        trading_status=HistoricalTradingStatus.TRADING,
        st_status=None,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST",
            ArtifactId("raw-request-correctness"),
            canonical_hash({"request": "correctness"}),
        ),
        raw_row_number=row,
        missing_fields=("listing_status", "st_status"),
        limitations=("PIT_INCOMPLETE",),
    )
