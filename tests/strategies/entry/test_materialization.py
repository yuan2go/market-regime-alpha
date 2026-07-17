from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.candidates import CandidatePopulation
from market_regime_alpha.core.identity import DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime, FinalizationTime
from market_regime_alpha.data import (
    RehearsalEntryReferenceEvidence,
    RehearsalFutureDailyBar,
    RehearsalFuturePathEvidenceCompleteness,
    RehearsalFuturePathSessionReadiness,
    RehearsalFutureSuspensionEvidence,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.strategies.entry import (
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
        source_dataset_id=DatasetId("dataset-calendar-v1"), market="CN_A_SHARE",
        calendar_version=version, timezone_name="Asia/Shanghai",
        sessions=tuple(_session(value) for value in dates),
    )


def _decision_time() -> DecisionTime:
    return DecisionTime(_at(DECISION_DATE, 14, 55))


def _population(symbols: tuple[str, ...] = (SYMBOL,)) -> CandidatePopulation:
    return CandidatePopulation(UniverseId("universe-entry-path-v1"), _decision_time(), symbols, (DatasetId("dataset-population-v1"),))


def _reference(symbol: str = SYMBOL, *, price: float = 10.0, basis: str = PRICE_BASIS, source: DatasetId = REFERENCE_DATASET, available_at: AvailabilityTime | None = None) -> RehearsalEntryReferenceEvidence:
    return RehearsalEntryReferenceEvidence(symbol, _decision_time(), price, basis, available_at or AvailabilityTime(_at(DECISION_DATE, 14, 55)), source, "DECISION_REFERENCE_ASSERTION_V1")


def _bar(session_date: date, *, symbol: str = SYMBOL, open_price: float = 10.0, high: float = 10.1, low: float = 9.9, close: float = 10.0, basis: str = PRICE_BASIS, source: DatasetId = FUTURE_DATASET) -> RehearsalFutureDailyBar:
    return RehearsalFutureDailyBar(symbol, session_date, open_price, high, low, close, basis, source, AvailabilityTime(_at(session_date, 15, 5)), FinalizationTime(_at(session_date, 15, 1)))


def _suspension(session_date: date, *, symbol: str = SYMBOL, is_suspended: bool = True, source: DatasetId = FUTURE_DATASET) -> RehearsalFutureSuspensionEvidence:
    return RehearsalFutureSuspensionEvidence(symbol, session_date, is_suspended, source, AvailabilityTime(_at(session_date, 15, 6)), FinalizationTime(_at(session_date, 15, 1)))


def _completeness(symbols: tuple[str, ...] = (SYMBOL,), *, available_at: AvailabilityTime | None = None, coverage_through: date = HORIZON_DATES[-1], readiness_minute: int = 30) -> RehearsalFuturePathEvidenceCompleteness:
    return RehearsalFuturePathEvidenceCompleteness(
        FUTURE_DATASET, available_at or AvailabilityTime(_at(HORIZON_DATES[-1], 15, 30)),
        "FUTURE_PATH_COVERAGE_ASSERTION_V1", tuple(sorted(symbols)), coverage_through,
        tuple(RehearsalFuturePathSessionReadiness(value, AvailabilityTime(_at(value, 15, readiness_minute))) for value in HORIZON_DATES),
    )


def _contract():
    return build_entry_path_target_contract(EntryBarrierSpec(0.02, -0.02, 3, PRICE_BASIS))


def _materialize(*, bars: tuple[RehearsalFutureDailyBar, ...] = (), references: tuple[RehearsalEntryReferenceEvidence, ...] | None = None, suspensions: tuple[RehearsalFutureSuspensionEvidence, ...] = (), population: CandidatePopulation | None = None, completeness: RehearsalFuturePathEvidenceCompleteness | None = None, materialized_at: AsOfTime | None = None, calendar=None, source_dataset_ids: tuple[DatasetId, ...] = (FUTURE_DATASET, REFERENCE_DATASET)):
    resolved_population = population or _population()
    return materialize_entry_path_target(
        contract=_contract(), population=resolved_population, source_dataset_ids=source_dataset_ids,
        trading_calendar=calendar or _calendar(),
        entry_reference_evidence=references if references is not None else tuple(_reference(symbol) for symbol in resolved_population.symbols),
        future_daily_bars=bars, future_suspensions=suspensions,
        future_path_evidence_completeness=completeness or _completeness(resolved_population.symbols),
        materialized_at=materialized_at or AsOfTime(_at(HORIZON_DATES[-1], 16, 0)),
        code_revision="abc123", config_hash="sha256:entry-config",
    )


@pytest.mark.parametrize(("bar", "outcome", "trigger"), (
    (_bar(HORIZON_DATES[0], open_price=10.3, high=10.4, low=10.1, close=10.2), EntryPathOutcome.UP_FIRST, EntryPathTriggerType.OPEN_GAP_UP),
    (_bar(HORIZON_DATES[0], open_price=9.7, high=9.9, low=9.6, close=9.8), EntryPathOutcome.DOWN_FIRST, EntryPathTriggerType.OPEN_GAP_DOWN),
    (_bar(HORIZON_DATES[0], high=10.2, low=9.9), EntryPathOutcome.UP_FIRST, EntryPathTriggerType.INTRADAY_HIGH_ONLY),
    (_bar(HORIZON_DATES[0], high=10.1, low=9.8), EntryPathOutcome.DOWN_FIRST, EntryPathTriggerType.INTRADAY_LOW_ONLY),
))
def test_existing_barrier_classification_is_preserved(bar, outcome, trigger) -> None:
    observation = _materialize(bars=(bar,)).observations[0]
    assert (observation.status, observation.outcome, observation.trigger_type) == (EntryPathObservationStatus.AVAILABLE, outcome, trigger)
    assert observation.reason_code is EntryPathReasonCode.OUTCOME_RESOLVED


def test_dual_touch_and_timeout_are_preserved() -> None:
    ambiguous = _materialize(bars=(_bar(HORIZON_DATES[0], high=10.2, low=9.8),)).observations[0]
    assert ambiguous.status is EntryPathObservationStatus.AMBIGUOUS
    assert ambiguous.reason_code is EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
    timeout = _materialize(bars=tuple(_bar(value) for value in HORIZON_DATES)).observations[0]
    assert timeout.outcome is EntryPathOutcome.TIMEOUT
    assert timeout.reason_code is EntryPathReasonCode.HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH


def test_reference_basis_mismatch_fails_closed_and_aligned_basis_passes() -> None:
    with pytest.raises(ValueError, match="reference.*basis"):
        _materialize(references=(_reference(basis="FORWARD_ADJUSTED_V1"),))
    assert _materialize(bars=(_bar(HORIZON_DATES[0]),)).observations[0].reference_price == 10.0


@pytest.mark.parametrize("references", ((), (_reference(), _reference()), (_reference("000002.SZ"),)))
def test_reference_population_coverage_is_structural(references) -> None:
    with pytest.raises(ValueError, match="reference evidence"):
        _materialize(references=references)


def test_closed_before_readiness_is_not_yet_observed() -> None:
    completeness = _completeness(available_at=AvailabilityTime(_at(HORIZON_DATES[0], 15, 5)))
    observation = _materialize(completeness=completeness, materialized_at=AsOfTime(_at(HORIZON_DATES[0], 15, 10))).observations[0]
    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.reason_code is EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE


def test_watermark_not_covered_is_not_yet_observed() -> None:
    completeness = _completeness(coverage_through=DECISION_DATE)
    observation = _materialize(completeness=completeness).observations[0]
    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.reason_code is EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE


def test_unavailable_completeness_assertion_is_not_used_as_coverage() -> None:
    completeness = _completeness(
        available_at=AvailabilityTime(_at(HORIZON_DATES[0], 15, 40))
    )
    observation = _materialize(
        completeness=completeness,
        materialized_at=AsOfTime(_at(HORIZON_DATES[0], 15, 35)),
    ).observations[0]
    assert observation.status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert observation.reason_code is EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE


def test_covered_missing_bar_is_observed_at_completeness_availability() -> None:
    completeness = _completeness(available_at=AvailabilityTime(_at(HORIZON_DATES[-1], 15, 31)))
    observation = _materialize(completeness=completeness).observations[0]
    assert observation.status is EntryPathObservationStatus.MISSING
    assert observation.observed_at == completeness.available_at
    assert observation.reason_code is EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING


def test_completeness_requires_exact_population_and_horizon_readiness() -> None:
    with pytest.raises(ValueError, match="covered_symbols"):
        _materialize(completeness=_completeness((SYMBOL, "000002.SZ")))
    bad = replace(_completeness(), session_readiness=(RehearsalFuturePathSessionReadiness(HORIZON_DATES[0], AvailabilityTime(_at(HORIZON_DATES[0], 15, 30))),))
    with pytest.raises(ValueError, match="readiness"):
        _materialize(completeness=bad)


def test_future_lineage_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="source Dataset"):
        _materialize(bars=(_bar(HORIZON_DATES[0], source=REFERENCE_DATASET),))


def test_identity_is_order_invariant_and_sensitive_to_evidence_semantics() -> None:
    symbols = (SYMBOL, "000002.SZ")
    population = _population(symbols)
    references = tuple(_reference(symbol) for symbol in symbols)
    bars = tuple(_bar(HORIZON_DATES[0], symbol=symbol, high=10.3) for symbol in symbols)
    first = _materialize(population=population, references=references, bars=bars)
    reordered = _materialize(population=population, references=tuple(reversed(references)), bars=tuple(reversed(bars)))
    changed_reference = _materialize(population=population, references=(replace(references[0], reference_price=10.1), references[1]), bars=bars)
    changed_readiness = _materialize(population=population, references=references, bars=bars, completeness=_completeness(symbols, readiness_minute=31))
    assert first.artifact_id == reordered.artifact_id
    assert first.artifact_id != changed_reference.artifact_id
    assert first.artifact_id != changed_readiness.artifact_id
    assert first.entry_reference_evidence_ids == tuple(item.evidence_id for item in references)


def test_suspension_consumption_and_calendar_coverage_remain_strict() -> None:
    result = _materialize(bars=(_bar(HORIZON_DATES[1], high=10.3),), suspensions=(_suspension(HORIZON_DATES[0]),))
    assert result.observations[0].outcome is EntryPathOutcome.UP_FIRST
    assert result.consumed_future_suspension_evidence_ids == (_suspension(HORIZON_DATES[0]).evidence_id,)
    with pytest.raises(LookupError):
        _materialize(calendar=_calendar(covered=3))
