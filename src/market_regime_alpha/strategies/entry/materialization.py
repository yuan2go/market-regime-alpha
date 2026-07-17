"""Pure daily-OHLC materialization of Entry competing-event research Targets."""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates import CandidatePopulation
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime
from market_regime_alpha.data import (
    RehearsalEntryReferenceEvidence,
    RehearsalFutureDailyBar,
    RehearsalFuturePathEvidenceCompleteness,
    RehearsalFutureSuspensionEvidence,
    TradingCalendarArtifact,
    TradingSession,
)
from market_regime_alpha.strategies.entry.contracts import (
    DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1,
    DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1,
    ENTRY_PATH_TARGET_SCHEMA_VERSION,
    NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1,
    EntryPathObservation,
    EntryPathObservationStatus,
    EntryPathOutcome,
    EntryPathReasonCode,
    EntryPathTargetContract,
    EntryPathTargetMaterialization,
    EntryPathTriggerType,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


def materialize_entry_path_target(*, contract: EntryPathTargetContract, population: CandidatePopulation, source_dataset_ids: tuple[DatasetId, ...], trading_calendar: TradingCalendarArtifact, entry_reference_evidence: tuple[RehearsalEntryReferenceEvidence, ...], future_daily_bars: tuple[RehearsalFutureDailyBar, ...], future_suspensions: tuple[RehearsalFutureSuspensionEvidence, ...], future_path_evidence_completeness: RehearsalFuturePathEvidenceCompleteness, materialized_at: AsOfTime, code_revision: str, config_hash: str) -> EntryPathTargetMaterialization:
    """Materialize an identified Target without inferring price basis or coverage."""
    _validate_request(contract, population, source_dataset_ids, trading_calendar, materialized_at, code_revision, config_hash)
    horizon_dates = trading_calendar.resolve_following_session_dates(population.decision_time, contract.spec.horizon_sessions)
    source_ids = tuple(sorted(source_dataset_ids, key=str))
    sessions = {item.trade_date: item for item in trading_calendar.sessions}
    population_symbols = set(population.symbols)
    completeness = future_path_evidence_completeness
    if completeness.source_dataset_id not in source_ids:
        raise ValueError("completeness source Dataset is not declared")
    if completeness.covered_symbols != population.symbols:
        raise ValueError("completeness covered_symbols must exactly equal Candidate Population")
    readiness = _validate_readiness(completeness, horizon_dates, sessions)
    references = _index_references(entry_reference_evidence, population, source_ids, contract)
    bars = _index_bars(future_daily_bars, population_symbols, horizon_dates, sessions, materialized_at, source_ids, completeness, contract, references)
    suspensions = _index_suspensions(future_suspensions, population_symbols, horizon_dates, sessions, materialized_at, source_ids, completeness)
    for key, evidence in suspensions.items():
        if evidence.is_suspended and key in bars:
            raise ValueError("confirmed suspension conflicts with future daily bar evidence")

    observations: list[EntryPathObservation] = []
    bar_ids: list[ArtifactId] = []
    suspension_ids: list[ArtifactId] = []
    for symbol in population.symbols:
        observation, used_bars, used_suspensions = _evaluate_symbol(symbol, contract, references[symbol], horizon_dates, sessions, readiness, completeness, bars, suspensions, materialized_at)
        observations.append(observation)
        bar_ids.extend(used_bars)
        suspension_ids.extend(used_suspensions)
    reference_ids = tuple(references[symbol].evidence_id for symbol in population.symbols)
    ordered_bars = tuple(sorted(set(bar_ids), key=str))
    ordered_suspensions = tuple(sorted(set(suspension_ids), key=str))
    values = tuple(observations)
    artifact_id = _artifact_id(contract, population, source_ids, trading_calendar, materialized_at, code_revision, config_hash, reference_ids, ordered_bars, ordered_suspensions, completeness.evidence_id, values)
    return EntryPathTargetMaterialization(artifact_id, contract.target_id, source_ids, trading_calendar.artifact_id, population.universe_id, population.decision_time, materialized_at, code_revision, config_hash, reference_ids, ordered_bars, ordered_suspensions, completeness.evidence_id, values)


def _validate_request(contract: EntryPathTargetContract, population: CandidatePopulation, source_dataset_ids: tuple[DatasetId, ...], calendar: TradingCalendarArtifact, materialized_at: AsOfTime, code_revision: str, config_hash: str) -> None:
    if not isinstance(contract, EntryPathTargetContract) or not isinstance(population, CandidatePopulation):
        raise TypeError("contract and population must use their canonical contracts")
    if not isinstance(calendar, TradingCalendarArtifact) or not isinstance(materialized_at, AsOfTime):
        raise TypeError("trading_calendar and materialized_at must use their canonical contracts")
    if not source_dataset_ids or len(source_dataset_ids) != len(set(source_dataset_ids)):
        raise ValueError("source_dataset_ids must be non-empty and unique")
    if any(not isinstance(value, DatasetId) for value in source_dataset_ids):
        raise TypeError("source_dataset_ids must contain DatasetId values")
    if materialized_at.value <= population.decision_time.value:
        raise ValueError("materialized_at must be after Decision Time")
    if calendar.timezone_name != "Asia/Shanghai":
        raise ValueError("Entry path V1 requires Asia/Shanghai Trading Calendar")
    local = population.decision_time.value.astimezone(_SHANGHAI)
    if (local.hour, local.minute, local.second, local.microsecond) != (14, 55, 0, 0):
        raise ValueError("Entry path V1 requires 14:55:00 Asia/Shanghai Decision Time")
    if not all(isinstance(value, str) and value.strip() == value and value for value in (code_revision, config_hash)):
        raise ValueError("code_revision and config_hash must be non-empty trimmed strings")
    spec = contract.spec
    if not (spec.schema_version == ENTRY_PATH_TARGET_SCHEMA_VERSION and spec.target_start_convention == NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1 and spec.reference_price_convention == DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1 and spec.path_ordering_convention == DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1):
        raise ValueError("Entry path materializer supports only the approved V1 conventions")


def _validate_readiness(completeness: RehearsalFuturePathEvidenceCompleteness, horizon: tuple[date, ...], sessions: dict[date, TradingSession]) -> dict[date, AvailabilityTime]:
    dates = tuple(item.session_date for item in completeness.session_readiness)
    if dates != horizon:
        raise ValueError("completeness readiness must exactly cover Target horizon")
    result: dict[date, AvailabilityTime] = {}
    for item in completeness.session_readiness:
        if item.evidence_ready_at.value < sessions[item.session_date].session_close:
            raise ValueError("readiness deadline is before TradingSession close")
        result[item.session_date] = item.evidence_ready_at
    return result


def _index_references(values: tuple[RehearsalEntryReferenceEvidence, ...], population: CandidatePopulation, source_ids: tuple[DatasetId, ...], contract: EntryPathTargetContract) -> dict[str, RehearsalEntryReferenceEvidence]:
    indexed: dict[str, RehearsalEntryReferenceEvidence] = {}
    for evidence in values:
        if evidence.symbol in indexed:
            raise ValueError("duplicate reference evidence")
        if evidence.symbol not in population.symbols:
            raise ValueError("reference evidence symbol is outside Candidate Population")
        if evidence.decision_time != population.decision_time:
            raise ValueError("reference evidence has wrong Decision Time")
        if evidence.source_dataset_id not in source_ids:
            raise ValueError("reference evidence source Dataset is not declared")
        if evidence.price_adjustment_basis != contract.spec.price_adjustment_basis:
            raise ValueError("reference evidence price adjustment basis mismatch")
        indexed[evidence.symbol] = evidence
    if set(indexed) != set(population.symbols):
        raise ValueError("reference evidence must exactly cover Candidate Population")
    return indexed


def _index_bars(values: tuple[RehearsalFutureDailyBar, ...], symbols: set[str], horizon: tuple[date, ...], sessions: dict[date, TradingSession], materialized_at: AsOfTime, source_ids: tuple[DatasetId, ...], completeness: RehearsalFuturePathEvidenceCompleteness, contract: EntryPathTargetContract, references: dict[str, RehearsalEntryReferenceEvidence]) -> dict[tuple[str, date], RehearsalFutureDailyBar]:
    indexed: dict[tuple[str, date], RehearsalFutureDailyBar] = {}
    for bar in values:
        _validate_future_scope(bar.symbol, bar.session_date, symbols, horizon, sessions)
        key = (bar.symbol, bar.session_date)
        if key in indexed:
            raise ValueError("duplicate future daily bar")
        if bar.source_dataset_id not in source_ids or bar.source_dataset_id != completeness.source_dataset_id:
            raise ValueError("future daily bar source Dataset conflicts with completeness")
        if bar.price_adjustment_basis != contract.spec.price_adjustment_basis or bar.price_adjustment_basis != references[bar.symbol].price_adjustment_basis:
            raise ValueError("future daily bar price adjustment basis mismatch")
        _validate_future_time("future daily bar", sessions[bar.session_date].session_close, bar.finalized_at.value, bar.available_at.value, materialized_at)
        indexed[key] = bar
    return indexed


def _index_suspensions(values: tuple[RehearsalFutureSuspensionEvidence, ...], symbols: set[str], horizon: tuple[date, ...], sessions: dict[date, TradingSession], materialized_at: AsOfTime, source_ids: tuple[DatasetId, ...], completeness: RehearsalFuturePathEvidenceCompleteness) -> dict[tuple[str, date], RehearsalFutureSuspensionEvidence]:
    indexed: dict[tuple[str, date], RehearsalFutureSuspensionEvidence] = {}
    for evidence in values:
        _validate_future_scope(evidence.symbol, evidence.session_date, symbols, horizon, sessions)
        key = (evidence.symbol, evidence.session_date)
        if key in indexed:
            raise ValueError("duplicate future suspension evidence")
        if evidence.source_dataset_id not in source_ids or evidence.source_dataset_id != completeness.source_dataset_id:
            raise ValueError("future suspension source Dataset conflicts with completeness")
        _validate_future_time("future suspension evidence", sessions[evidence.session_date].session_close, evidence.finalized_at.value, evidence.available_at.value, materialized_at)
        indexed[key] = evidence
    return indexed


def _validate_future_scope(symbol: str, session_date: date, symbols: set[str], horizon: tuple[date, ...], sessions: dict[date, TradingSession]) -> None:
    if symbol not in symbols:
        raise ValueError("future evidence symbol is outside Candidate Population")
    if session_date not in sessions:
        raise ValueError("future evidence session date is off-Calendar")
    if session_date not in horizon:
        raise ValueError("future evidence is outside resolved Target horizon")


def _validate_future_time(label: str, close: datetime, finalized_at: datetime, available_at: datetime, materialized_at: AsOfTime) -> None:
    if finalized_at < close:
        raise ValueError(f"{label} finalized before TradingSession close")
    if available_at > materialized_at.value:
        raise ValueError(f"{label} is available after materialized_at")


def _evaluate_symbol(symbol: str, contract: EntryPathTargetContract, reference: RehearsalEntryReferenceEvidence, horizon: tuple[date, ...], sessions: dict[date, TradingSession], readiness: dict[date, AvailabilityTime], completeness: RehearsalFuturePathEvidenceCompleteness, bars: dict[tuple[str, date], RehearsalFutureDailyBar], suspensions: dict[tuple[str, date], RehearsalFutureSuspensionEvidence], materialized_at: AsOfTime) -> tuple[EntryPathObservation, tuple[ArtifactId, ...], tuple[ArtifactId, ...]]:
    reference_price = float(reference.reference_price)
    upper = reference_price * (1.0 + contract.spec.upper_return)
    lower = reference_price * (1.0 + contract.spec.lower_return)
    evaluated: list[date] = []
    used_bars: list[ArtifactId] = []
    used_suspensions: list[ArtifactId] = []
    latest: AvailabilityTime | None = None
    for index, session_date in enumerate(horizon, start=1):
        if materialized_at.value < sessions[session_date].session_close:
            return _pending(symbol, reference_price, upper, lower, evaluated, EntryPathReasonCode.HORIZON_NOT_COMPLETE), tuple(used_bars), tuple(used_suspensions)
        if materialized_at.value < readiness[session_date].value:
            return _pending(symbol, reference_price, upper, lower, evaluated, EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE), tuple(used_bars), tuple(used_suspensions)
        if (
            completeness.available_at.value > materialized_at.value
            or completeness.coverage_through_session_date < session_date
        ):
            return _pending(symbol, reference_price, upper, lower, evaluated, EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE), tuple(used_bars), tuple(used_suspensions)
        key = (symbol, session_date)
        bar = bars.get(key)
        suspension = suspensions.get(key)
        if bar is None and not (suspension and suspension.is_suspended):
            return EntryPathObservation(symbol, EntryPathObservationStatus.MISSING, None, reference_price, upper, lower, None, None, None, tuple(evaluated), session_date, EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING, completeness.available_at), tuple(used_bars), tuple(used_suspensions)
        if bar is None:
            assert suspension is not None
            evaluated.append(session_date)
            used_suspensions.append(suspension.evidence_id)
            latest = suspension.available_at
            continue
        evaluated.append(session_date)
        used_bars.append(bar.evidence_id)
        latest = bar.available_at
        resolved = _classify_bar(bar, upper, lower)
        if resolved is not None:
            status, outcome, trigger, reason = resolved
            return EntryPathObservation(symbol, status, outcome, reference_price, upper, lower, session_date, index, trigger, tuple(evaluated), None, reason, bar.available_at), tuple(used_bars), tuple(used_suspensions)
    assert latest is not None
    return EntryPathObservation(symbol, EntryPathObservationStatus.AVAILABLE, EntryPathOutcome.TIMEOUT, reference_price, upper, lower, horizon[-1], len(horizon), EntryPathTriggerType.HORIZON_EXHAUSTED, tuple(evaluated), None, EntryPathReasonCode.HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH, latest), tuple(used_bars), tuple(used_suspensions)


def _pending(symbol: str, reference: float, upper: float, lower: float, evaluated: list[date], reason: EntryPathReasonCode) -> EntryPathObservation:
    return EntryPathObservation(symbol, EntryPathObservationStatus.NOT_YET_OBSERVED, None, reference, upper, lower, None, None, None, tuple(evaluated), None, reason, None)


def _classify_bar(bar: RehearsalFutureDailyBar, upper: float, lower: float) -> tuple[EntryPathObservationStatus, EntryPathOutcome | None, EntryPathTriggerType, EntryPathReasonCode] | None:
    if bar.open >= upper:
        return EntryPathObservationStatus.AVAILABLE, EntryPathOutcome.UP_FIRST, EntryPathTriggerType.OPEN_GAP_UP, EntryPathReasonCode.OUTCOME_RESOLVED
    if bar.open <= lower:
        return EntryPathObservationStatus.AVAILABLE, EntryPathOutcome.DOWN_FIRST, EntryPathTriggerType.OPEN_GAP_DOWN, EntryPathReasonCode.OUTCOME_RESOLVED
    if bar.high >= upper and bar.low <= lower:
        return EntryPathObservationStatus.AMBIGUOUS, None, EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED, EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
    if bar.high >= upper:
        return EntryPathObservationStatus.AVAILABLE, EntryPathOutcome.UP_FIRST, EntryPathTriggerType.INTRADAY_HIGH_ONLY, EntryPathReasonCode.OUTCOME_RESOLVED
    if bar.low <= lower:
        return EntryPathObservationStatus.AVAILABLE, EntryPathOutcome.DOWN_FIRST, EntryPathTriggerType.INTRADAY_LOW_ONLY, EntryPathReasonCode.OUTCOME_RESOLVED
    return None


def _artifact_id(contract: EntryPathTargetContract, population: CandidatePopulation, sources: tuple[DatasetId, ...], calendar: TradingCalendarArtifact, materialized_at: AsOfTime, revision: str, config: str, references: tuple[ArtifactId, ...], bars: tuple[ArtifactId, ...], suspensions: tuple[ArtifactId, ...], completeness: ArtifactId, observations: tuple[EntryPathObservation, ...]) -> ArtifactId:
    payload = {"schema_version": "entry-path-materialization-v1", "target_id": str(contract.target_id), "source_dataset_ids": [str(value) for value in sources], "calendar_artifact_id": str(calendar.artifact_id), "universe_id": str(population.universe_id), "decision_time": population.decision_time.isoformat(), "population_symbols": list(population.symbols), "materialized_at": materialized_at.isoformat(), "code_revision": revision, "config_hash": config, "entry_reference_evidence_ids": [str(value) for value in references], "consumed_future_bar_evidence_ids": [str(value) for value in bars], "consumed_future_suspension_evidence_ids": [str(value) for value in suspensions], "completeness_evidence_id": str(completeness), "observations": [_observation_payload(value) for value in observations]}
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return ArtifactId(f"entry-path-materialization-{sha256(canonical.encode('utf-8')).hexdigest()[:24]}")


def _observation_payload(value: EntryPathObservation) -> dict[str, object]:
    return {"symbol": value.symbol, "status": value.status.value, "outcome": value.outcome.value if value.outcome else None, "reference_price": value.reference_price, "upper_price": value.upper_price, "lower_price": value.lower_price, "event_session_date": value.event_session_date.isoformat() if value.event_session_date else None, "event_session_index": value.event_session_index, "trigger_type": value.trigger_type.value if value.trigger_type else None, "evaluated_session_dates": [item.isoformat() for item in value.evaluated_session_dates], "first_missing_session_date": value.first_missing_session_date.isoformat() if value.first_missing_session_date else None, "reason_code": value.reason_code.value, "observed_at": value.observed_at.isoformat() if value.observed_at else None}
