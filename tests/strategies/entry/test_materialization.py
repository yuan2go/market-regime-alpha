from __future__ import annotations

from dataclasses import replace
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
    RehearsalEntryReferenceEvidence,
    RehearsalFutureDailyBar,
    RehearsalFuturePathCoverageAssertion,
    RehearsalFuturePathReadinessPolicy,
    RehearsalFuturePathSessionReadiness,
    RehearsalFutureSuspensionEvidence,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.strategies.entry import (
    ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION,
    ENTRY_PATH_OBSERVATION_SCHEMA_VERSION,
    EntryBarrierSpec,
    EntryPathObservationStatus,
    EntryPathOutcome,
    EntryPathReasonCode,
    EntryPathTriggerType,
    build_entry_path_target_contract,
    materialize_entry_path_target,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_DATE = date(2026, 7, 15)
HORIZON_DATES = (date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22))
SYMBOL = "000001.SZ"
PRICE_BASIS = "RAW_UNADJUSTED_TRADABLE_PRICE_V1"
REFERENCE_DATASET = DatasetId("dataset-entry-reference-v1")
FUTURE_DATASET = DatasetId("dataset-entry-future-v1")


def _at(value: date, hour: int, minute: int) -> datetime:
    return datetime(value.year, value.month, value.day, hour, minute, tzinfo=TZ)


def _session(value: date) -> TradingSession:
    return TradingSession(value, _at(value, 15, 0))


def _calendar(*, version: str = "fixture-v1", covered: int = 5):
    dates = (DECISION_DATE, *HORIZON_DATES, date(2026, 7, 23))[:covered]
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version=version,
        timezone_name="Asia/Shanghai",
        sessions=tuple(_session(value) for value in dates),
    )


def _decision_time() -> DecisionTime:
    return DecisionTime(_at(DECISION_DATE, 14, 55))


def _population(symbols: tuple[str, ...] = (SYMBOL,)) -> CandidatePopulation:
    return CandidatePopulation(
        UniverseId("universe-entry-path-v1"),
        _decision_time(),
        symbols,
        (DatasetId("dataset-population-v1"),),
    )


def _reference(
    symbol: str = SYMBOL,
    *,
    price: float = 10.0,
    basis: str = PRICE_BASIS,
    source: DatasetId = REFERENCE_DATASET,
    available_at: AvailabilityTime | None = None,
) -> RehearsalEntryReferenceEvidence:
    return RehearsalEntryReferenceEvidence(
        symbol,
        _decision_time(),
        price,
        basis,
        available_at or AvailabilityTime(_at(DECISION_DATE, 14, 55)),
        source,
        "DECISION_REFERENCE_ASSERTION_V1",
    )


def _bar(
    session_date: date,
    *,
    symbol: str = SYMBOL,
    open_price: float = 10.0,
    high: float = 10.1,
    low: float = 9.9,
    close: float = 10.0,
    basis: str = PRICE_BASIS,
    source: DatasetId = FUTURE_DATASET,
    available_at: AvailabilityTime | None = None,
    finalized_at: FinalizationTime | None = None,
) -> RehearsalFutureDailyBar:
    return RehearsalFutureDailyBar(
        symbol,
        session_date,
        open_price,
        high,
        low,
        close,
        basis,
        source,
        available_at or AvailabilityTime(_at(session_date, 15, 5)),
        finalized_at or FinalizationTime(_at(session_date, 15, 1)),
    )


def _suspension(
    session_date: date,
    *,
    symbol: str = SYMBOL,
    is_suspended: bool = True,
    source: DatasetId = FUTURE_DATASET,
    available_at: AvailabilityTime | None = None,
    finalized_at: FinalizationTime | None = None,
) -> RehearsalFutureSuspensionEvidence:
    return RehearsalFutureSuspensionEvidence(
        symbol,
        session_date,
        is_suspended,
        source,
        available_at or AvailabilityTime(_at(session_date, 15, 6)),
        finalized_at or FinalizationTime(_at(session_date, 15, 1)),
    )


def _policy(
    *,
    readiness_minute: int = 30,
    effective_at: AvailabilityTime | None = None,
) -> RehearsalFuturePathReadinessPolicy:
    return RehearsalFuturePathReadinessPolicy(
        FUTURE_DATASET,
        "FUTURE_PATH_READINESS_POLICY_V1",
        effective_at or AvailabilityTime(_at(DECISION_DATE, 14, 50)),
        tuple(
            RehearsalFuturePathSessionReadiness(
                value,
                AvailabilityTime(_at(value, 15, readiness_minute)),
            )
            for value in HORIZON_DATES
        ),
    )


def _coverage(
    symbols: tuple[str, ...] = (SYMBOL,),
    *,
    available_at: AvailabilityTime | None = None,
    coverage_through: date = HORIZON_DATES[-1],
    convention: str = "FUTURE_PATH_COVERAGE_ASSERTION_V1",
) -> RehearsalFuturePathCoverageAssertion:
    return RehearsalFuturePathCoverageAssertion(
        FUTURE_DATASET,
        available_at or AvailabilityTime(_at(HORIZON_DATES[-1], 15, 30)),
        convention,
        tuple(sorted(symbols)),
        coverage_through,
    )


def _contract():
    return build_entry_path_target_contract(
        EntryBarrierSpec(0.02, -0.02, 3, PRICE_BASIS)
    )


def _materialize(
    *,
    bars: tuple[RehearsalFutureDailyBar, ...] = (),
    references: tuple[RehearsalEntryReferenceEvidence, ...] | None = None,
    suspensions: tuple[RehearsalFutureSuspensionEvidence, ...] = (),
    population: CandidatePopulation | None = None,
    policy: RehearsalFuturePathReadinessPolicy | None = None,
    coverage: RehearsalFuturePathCoverageAssertion | None = None,
    materialized_at: AsOfTime | None = None,
    calendar=None,
    source_dataset_ids: tuple[DatasetId, ...] = (FUTURE_DATASET, REFERENCE_DATASET),
):
    resolved_population = population or _population()
    return materialize_entry_path_target(
        contract=_contract(),
        population=resolved_population,
        source_dataset_ids=source_dataset_ids,
        trading_calendar=calendar or _calendar(),
        entry_reference_evidence=(
            references
            if references is not None
            else tuple(_reference(symbol) for symbol in resolved_population.symbols)
        ),
        future_daily_bars=bars,
        future_suspensions=suspensions,
        future_path_readiness_policy=policy or _policy(),
        future_path_coverage_assertion=coverage,
        materialized_at=materialized_at or AsOfTime(_at(HORIZON_DATES[-1], 16, 0)),
        code_revision="abc123",
        config_hash="sha256:entry-config",
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
            _bar(HORIZON_DATES[0], high=10.2, low=9.9),
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.INTRADAY_HIGH_ONLY,
        ),
        (
            _bar(HORIZON_DATES[0], high=10.1, low=9.8),
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.INTRADAY_LOW_ONLY,
        ),
    ),
)
def test_existing_barrier_classification_is_preserved(bar, outcome, trigger) -> None:
    observation = _materialize(bars=(bar,)).observations[0]
    assert (observation.status, observation.outcome, observation.trigger_type) == (
        EntryPathObservationStatus.AVAILABLE,
        outcome,
        trigger,
    )
    assert observation.reason_code is EntryPathReasonCode.OUTCOME_RESOLVED


def test_dual_touch_and_timeout_are_preserved() -> None:
    ambiguous = _materialize(
        bars=(_bar(HORIZON_DATES[0], high=10.2, low=9.8),)
    ).observations[0]
    assert ambiguous.status is EntryPathObservationStatus.AMBIGUOUS
    assert (
        ambiguous.reason_code
        is EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
    )
    timeout = _materialize(
        bars=tuple(_bar(value) for value in HORIZON_DATES)
    ).observations[0]
    assert timeout.outcome is EntryPathOutcome.TIMEOUT
    assert (
        timeout.reason_code
        is EntryPathReasonCode.HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH
    )


def test_v2_materialization_stores_v2_schema_and_readiness_policy_id() -> None:
    result = _materialize(bars=(_bar(HORIZON_DATES[0], high=10.3),))
    assert result.schema_version == ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION
    assert result.observation_schema_version == ENTRY_PATH_OBSERVATION_SCHEMA_VERSION
    assert result.readiness_policy_id == _policy().policy_id
    assert result.consumed_coverage_assertion_id is None


def test_reference_basis_mismatch_fails_closed_and_aligned_basis_passes() -> None:
    with pytest.raises(ValueError, match="reference.*basis"):
        _materialize(references=(_reference(basis="FORWARD_ADJUSTED_V1"),))
    assert _materialize(bars=(_bar(HORIZON_DATES[0]),)).observations[0].reference_price == 10.0


@pytest.mark.parametrize(
    "references",
    ((), (_reference(), _reference()), (_reference("000002.SZ"),)),
)
def test_reference_population_coverage_is_structural(references) -> None:
    with pytest.raises(ValueError, match="reference evidence"):
        _materialize(references=references)


def test_direct_bar_is_classified_before_readiness_and_does_not_consume_coverage() -> None:
    policy = _policy(readiness_minute=59)
    coverage = _coverage()
    result = _materialize(
        bars=(_bar(HORIZON_DATES[0], high=10.3),),
        policy=policy,
        coverage=coverage,
    )
    assert result.observations[0].outcome is EntryPathOutcome.UP_FIRST
    assert result.consumed_coverage_assertion_id is None


def test_confirmed_suspension_is_consumed_before_readiness() -> None:
    result = _materialize(
        policy=_policy(readiness_minute=59),
        suspensions=(_suspension(HORIZON_DATES[0]),),
        bars=(_bar(HORIZON_DATES[1], high=10.3),),
    )
    assert result.observations[0].outcome is EntryPathOutcome.UP_FIRST
    assert result.consumed_future_suspension_evidence_ids == (
        _suspension(HORIZON_DATES[0]).evidence_id,
    )


def test_absence_before_readiness_is_not_yet_observed() -> None:
    result = _materialize(
        coverage=None,
        materialized_at=AsOfTime(_at(HORIZON_DATES[0], 15, 10)),
    )
    observation = result.observations[0]
    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.reason_code is EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE
    assert result.consumed_coverage_assertion_id is None


def test_absence_after_readiness_without_coverage_is_not_yet_observed() -> None:
    result = _materialize(coverage=None)
    observation = result.observations[0]
    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.reason_code is EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE


def test_watermark_not_covered_is_not_yet_observed_and_is_consumed() -> None:
    coverage = _coverage(
        coverage_through=DECISION_DATE,
        available_at=AvailabilityTime(_at(DECISION_DATE, 15, 30)),
    )
    result = _materialize(coverage=coverage)
    assert result.observations[0].reason_code is EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE
    assert result.consumed_coverage_assertion_id == coverage.evidence_id


def test_covered_missing_bar_is_confirmed_at_coverage_availability() -> None:
    coverage = _coverage()
    result = _materialize(coverage=coverage)
    observation = result.observations[0]
    assert observation.status is EntryPathObservationStatus.MISSING
    assert observation.observed_at == coverage.available_at
    assert observation.reason_code is EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING
    assert result.consumed_coverage_assertion_id == coverage.evidence_id


@pytest.mark.parametrize(
    "factory",
    (
        lambda: _bar(
            HORIZON_DATES[0],
            available_at=AvailabilityTime(_at(HORIZON_DATES[-1], 16, 1)),
            finalized_at=FinalizationTime(_at(HORIZON_DATES[-1], 16, 0)),
        ),
        lambda: _suspension(
            HORIZON_DATES[0],
            available_at=AvailabilityTime(_at(HORIZON_DATES[-1], 16, 1)),
            finalized_at=FinalizationTime(_at(HORIZON_DATES[-1], 16, 0)),
        ),
    ),
)
def test_future_direct_evidence_fails_closed(factory) -> None:
    with pytest.raises(ValueError, match="available after materialized_at"):
        _materialize(bars=(factory(),) if isinstance(factory(), RehearsalFutureDailyBar) else (), suspensions=(factory(),) if isinstance(factory(), RehearsalFutureSuspensionEvidence) else ())


def test_future_coverage_fails_closed() -> None:
    coverage = _coverage(available_at=AvailabilityTime(_at(HORIZON_DATES[-1], 16, 1)))
    with pytest.raises(ValueError, match="coverage.*materialized_at"):
        _materialize(coverage=coverage)


def test_policy_effective_after_decision_fails_closed() -> None:
    with pytest.raises(ValueError, match="effective_at"):
        _materialize(policy=_policy(effective_at=AvailabilityTime(_at(DECISION_DATE, 15, 0))))


def test_coverage_requires_calendar_watermark_and_final_availability() -> None:
    with pytest.raises(ValueError, match="off-Calendar"):
        _materialize(
            coverage=_coverage(
                coverage_through=date(2026, 7, 19),
                available_at=AvailabilityTime(_at(date(2026, 7, 19), 15, 30)),
            )
        )
    with pytest.raises(ValueError, match="watermark.*close"):
        _materialize(
            coverage=_coverage(
                available_at=AvailabilityTime(_at(HORIZON_DATES[-1], 14, 59))
            )
        )


def test_watermark_after_target_horizon_is_accepted() -> None:
    coverage = _coverage(
        coverage_through=date(2026, 7, 23),
        available_at=AvailabilityTime(_at(date(2026, 7, 23), 15, 30)),
    )
    result = _materialize(
        coverage=coverage,
        materialized_at=AsOfTime(_at(date(2026, 7, 23), 16, 0)),
    )
    assert result.observations[0].status is EntryPathObservationStatus.MISSING


def test_policy_and_coverage_identity_have_consumed_semantics() -> None:
    direct = tuple(_bar(value) for value in HORIZON_DATES)
    first = _materialize(bars=direct, coverage=_coverage())
    changed_unconsumed = _materialize(
        bars=direct,
        coverage=_coverage(convention="FUTURE_PATH_COVERAGE_ASSERTION_V2"),
    )
    changed_policy = _materialize(bars=direct, policy=_policy(readiness_minute=31))
    missing_first = _materialize(coverage=_coverage())
    missing_changed = _materialize(
        coverage=_coverage(convention="FUTURE_PATH_COVERAGE_ASSERTION_V2")
    )
    assert first.artifact_id == changed_unconsumed.artifact_id
    assert first.artifact_id != changed_policy.artifact_id
    assert missing_first.artifact_id != missing_changed.artifact_id


def test_identity_is_order_invariant_and_materialization_validates_id_invariants() -> None:
    symbols = (SYMBOL, "000002.SZ")
    population = _population(symbols)
    references = tuple(_reference(symbol) for symbol in symbols)
    bars = tuple(_bar(HORIZON_DATES[0], symbol=symbol, high=10.3) for symbol in symbols)
    first = _materialize(population=population, references=references, bars=bars)
    reordered = _materialize(
        population=population,
        references=tuple(reversed(references)),
        bars=tuple(reversed(bars)),
    )
    assert first.artifact_id == reordered.artifact_id
    assert first.entry_reference_evidence_ids == tuple(
        sorted((item.evidence_id for item in references), key=str)
    )
    with pytest.raises(ValueError, match="entry_reference_evidence_ids"):
        replace(first, entry_reference_evidence_ids=())
    with pytest.raises(ValueError, match="sorted"):
        replace(first, entry_reference_evidence_ids=tuple(reversed(first.entry_reference_evidence_ids)))
    with pytest.raises(ValueError, match="entry-path-materialization-v2"):
        replace(first, schema_version="entry-path-materialization-v1")
    assert all(
        item.schema_version == ENTRY_PATH_OBSERVATION_SCHEMA_VERSION
        for item in first.observations
    )


def test_suspension_bar_conflict_and_calendar_horizon_remain_strict() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        _materialize(
            bars=(_bar(HORIZON_DATES[0]),),
            suspensions=(_suspension(HORIZON_DATES[0]),),
        )
    with pytest.raises(LookupError):
        _materialize(calendar=_calendar(covered=3))
