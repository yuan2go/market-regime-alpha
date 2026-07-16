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
    RehearsalDecisionSnapshot,
    RehearsalFutureDailyBar,
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
    EntryPathTargetContract,
    EntryPathTargetMaterialization,
    EntryPathTriggerType,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def materialize_entry_path_target(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    future_daily_bars: tuple[RehearsalFutureDailyBar, ...],
    future_suspensions: tuple[RehearsalFutureSuspensionEvidence, ...],
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> EntryPathTargetMaterialization:
    """Materialize one identified Entry path Target without guessing intrabar order."""

    _validate_request(
        contract=contract,
        population=population,
        source_dataset_ids=source_dataset_ids,
        trading_calendar=trading_calendar,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    horizon_dates = trading_calendar.resolve_following_session_dates(
        population.decision_time,
        contract.spec.horizon_sessions,
    )
    sorted_source_ids = tuple(sorted(source_dataset_ids, key=str))
    session_by_date = {
        session.trade_date: session for session in trading_calendar.sessions
    }
    population_symbols = set(population.symbols)

    snapshot_by_symbol: dict[str, RehearsalDecisionSnapshot] = {}
    for snapshot in decision_snapshots:
        if snapshot.decision_time != population.decision_time:
            raise ValueError("Decision snapshot has wrong Decision Time")
        if snapshot.symbol not in population_symbols:
            raise ValueError("Decision snapshot symbol is outside Candidate Population")
        if snapshot.symbol in snapshot_by_symbol:
            raise ValueError(f"duplicate Decision snapshot: {snapshot.symbol}")
        snapshot_by_symbol[snapshot.symbol] = snapshot

    bar_by_key: dict[tuple[str, date], RehearsalFutureDailyBar] = {}
    for bar in future_daily_bars:
        key = (bar.symbol, bar.session_date)
        if key in bar_by_key:
            raise ValueError(f"duplicate future daily bar: {bar.symbol} {bar.session_date}")
        _validate_evidence_scope(
            symbol=bar.symbol,
            session_date=bar.session_date,
            population_symbols=population_symbols,
            horizon_dates=horizon_dates,
            trading_calendar=trading_calendar,
        )
        if bar.price_adjustment_basis != contract.spec.price_adjustment_basis:
            raise ValueError("future daily bar price adjustment basis mismatch")
        _validate_evidence_time(
            label="future daily bar",
            session_close=session_by_date[bar.session_date].session_close,
            finalized_at=bar.finalized_at.value,
            available_at=bar.available_at.value,
            materialized_at=materialized_at,
        )
        bar_by_key[key] = bar

    suspension_by_key: dict[
        tuple[str, date], RehearsalFutureSuspensionEvidence
    ] = {}
    for evidence in future_suspensions:
        key = (evidence.symbol, evidence.session_date)
        if key in suspension_by_key:
            raise ValueError(
                f"duplicate future suspension evidence: {evidence.symbol} "
                f"{evidence.session_date}"
            )
        _validate_evidence_scope(
            symbol=evidence.symbol,
            session_date=evidence.session_date,
            population_symbols=population_symbols,
            horizon_dates=horizon_dates,
            trading_calendar=trading_calendar,
        )
        _validate_evidence_time(
            label="future suspension evidence",
            session_close=session_by_date[evidence.session_date].session_close,
            finalized_at=evidence.finalized_at.value,
            available_at=evidence.available_at.value,
            materialized_at=materialized_at,
        )
        suspension_by_key[key] = evidence

    for key, evidence in suspension_by_key.items():
        if evidence.is_suspended and key in bar_by_key:
            raise ValueError(
                "confirmed suspension conflicts with future daily bar evidence"
            )

    observations = tuple(
        _evaluate_symbol(
            symbol=symbol,
            contract=contract,
            snapshot=snapshot_by_symbol.get(symbol),
            horizon_dates=horizon_dates,
            session_by_date=session_by_date,
            bar_by_key=bar_by_key,
            suspension_by_key=suspension_by_key,
            materialized_at=materialized_at,
        )
        for symbol in population.symbols
    )
    artifact_id = _artifact_id(
        contract=contract,
        population=population,
        source_dataset_ids=sorted_source_ids,
        trading_calendar=trading_calendar,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=observations,
    )
    return EntryPathTargetMaterialization(
        artifact_id=artifact_id,
        target_id=contract.target_id,
        source_dataset_ids=sorted_source_ids,
        calendar_artifact_id=trading_calendar.artifact_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=observations,
    )


def _validate_request(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> None:
    if not isinstance(contract, EntryPathTargetContract):
        raise TypeError("contract must be an EntryPathTargetContract")
    if not isinstance(population, CandidatePopulation):
        raise TypeError("population must be a CandidatePopulation")
    if not isinstance(trading_calendar, TradingCalendarArtifact):
        raise TypeError("trading_calendar must be a TradingCalendarArtifact")
    if not isinstance(materialized_at, AsOfTime):
        raise TypeError("materialized_at must be an AsOfTime")
    if not source_dataset_ids:
        raise ValueError("Entry path materialization requires source Dataset identities")
    if len(source_dataset_ids) != len(set(source_dataset_ids)):
        raise ValueError("source_dataset_ids must be unique")
    if any(not isinstance(value, DatasetId) for value in source_dataset_ids):
        raise TypeError("source_dataset_ids must contain DatasetId values")
    _require_text("code_revision", code_revision)
    _require_text("config_hash", config_hash)
    if materialized_at.value <= population.decision_time.value:
        raise ValueError("materialized_at must be after Decision Time")
    if trading_calendar.timezone_name != "Asia/Shanghai":
        raise ValueError("Entry path V1 requires Asia/Shanghai Trading Calendar")
    local = population.decision_time.value.astimezone(_SHANGHAI)
    if (local.hour, local.minute, local.second, local.microsecond) != (14, 55, 0, 0):
        raise ValueError("Entry path V1 requires 14:55:00 Asia/Shanghai Decision Time")
    spec = contract.spec
    expected = (
        spec.schema_version == ENTRY_PATH_TARGET_SCHEMA_VERSION
        and spec.target_start_convention
        == NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
        and spec.reference_price_convention
        == DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1
        and spec.path_ordering_convention
        == DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1
    )
    if not expected:
        raise ValueError("Entry path materializer supports only the approved V1 conventions")


def _validate_evidence_scope(
    *,
    symbol: str,
    session_date: date,
    population_symbols: set[str],
    horizon_dates: tuple[date, ...],
    trading_calendar: TradingCalendarArtifact,
) -> None:
    if symbol not in population_symbols:
        raise ValueError("future evidence symbol is outside Candidate Population")
    if not trading_calendar.contains(session_date):
        raise ValueError("future evidence session date is off-Calendar")
    if session_date not in horizon_dates:
        raise ValueError("future evidence is outside resolved Target horizon")


def _validate_evidence_time(
    *,
    label: str,
    session_close: datetime,
    finalized_at: datetime,
    available_at: datetime,
    materialized_at: AsOfTime,
) -> None:
    if finalized_at < session_close:
        raise ValueError(f"{label} finalized before TradingSession close")
    if available_at > materialized_at.value:
        raise ValueError(f"{label} is available after materialized_at")


def _evaluate_symbol(
    *,
    symbol: str,
    contract: EntryPathTargetContract,
    snapshot: RehearsalDecisionSnapshot | None,
    horizon_dates: tuple[date, ...],
    session_by_date: dict[date, TradingSession],
    bar_by_key: dict[tuple[str, date], RehearsalFutureDailyBar],
    suspension_by_key: dict[
        tuple[str, date], RehearsalFutureSuspensionEvidence
    ],
    materialized_at: AsOfTime,
) -> EntryPathObservation:
    known_at = AvailabilityTime(materialized_at.value)
    if snapshot is None:
        return EntryPathObservation(
            symbol=symbol,
            status=EntryPathObservationStatus.INVALID,
            outcome=None,
            reference_price=None,
            upper_price=None,
            lower_price=None,
            event_session_date=None,
            event_session_index=None,
            trigger_type=None,
            evaluated_session_dates=(),
            first_missing_session_date=None,
            reason_code="DECISION_SNAPSHOT_MISSING",
            observed_at=known_at,
        )
    reference_price = float(snapshot.reference_price)
    upper_price = reference_price * (1.0 + contract.spec.upper_return)
    lower_price = reference_price * (1.0 + contract.spec.lower_return)
    evaluated: list[date] = []
    final_evidence_available_at: AvailabilityTime | None = None
    for session_index, session_date in enumerate(horizon_dates, start=1):
        key = (symbol, session_date)
        bar = bar_by_key.get(key)
        suspension = suspension_by_key.get(key)
        if bar is not None:
            evaluated.append(session_date)
            final_evidence_available_at = bar.available_at
            resolved = _classify_bar(
                bar=bar,
                upper_price=upper_price,
                lower_price=lower_price,
            )
            if resolved is not None:
                status, outcome, trigger, reason = resolved
                return EntryPathObservation(
                    symbol=symbol,
                    status=status,
                    outcome=outcome,
                    reference_price=reference_price,
                    upper_price=upper_price,
                    lower_price=lower_price,
                    event_session_date=session_date,
                    event_session_index=session_index,
                    trigger_type=trigger,
                    evaluated_session_dates=tuple(evaluated),
                    first_missing_session_date=None,
                    reason_code=reason,
                    observed_at=bar.available_at,
                )
            continue
        if suspension is not None and suspension.is_suspended:
            evaluated.append(session_date)
            final_evidence_available_at = suspension.available_at
            continue
        session_close = session_by_date[session_date].session_close
        if materialized_at.value < session_close:
            return EntryPathObservation(
                symbol=symbol,
                status=EntryPathObservationStatus.NOT_YET_OBSERVED,
                outcome=None,
                reference_price=reference_price,
                upper_price=upper_price,
                lower_price=lower_price,
                event_session_date=None,
                event_session_index=None,
                trigger_type=None,
                evaluated_session_dates=tuple(evaluated),
                first_missing_session_date=None,
                reason_code="HORIZON_NOT_COMPLETE",
                observed_at=None,
            )
        return EntryPathObservation(
            symbol=symbol,
            status=EntryPathObservationStatus.MISSING,
            outcome=None,
            reference_price=reference_price,
            upper_price=upper_price,
            lower_price=lower_price,
            event_session_date=None,
            event_session_index=None,
            trigger_type=None,
            evaluated_session_dates=tuple(evaluated),
            first_missing_session_date=session_date,
            reason_code="FUTURE_DAILY_BAR_MISSING",
            observed_at=known_at,
        )
    assert final_evidence_available_at is not None
    return EntryPathObservation(
        symbol=symbol,
        status=EntryPathObservationStatus.AVAILABLE,
        outcome=EntryPathOutcome.TIMEOUT,
        reference_price=reference_price,
        upper_price=upper_price,
        lower_price=lower_price,
        event_session_date=horizon_dates[-1],
        event_session_index=len(horizon_dates),
        trigger_type=EntryPathTriggerType.HORIZON_EXHAUSTED,
        evaluated_session_dates=tuple(evaluated),
        first_missing_session_date=None,
        reason_code="HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH",
        observed_at=final_evidence_available_at,
    )


def _classify_bar(
    *,
    bar: RehearsalFutureDailyBar,
    upper_price: float,
    lower_price: float,
) -> tuple[
    EntryPathObservationStatus,
    EntryPathOutcome | None,
    EntryPathTriggerType,
    str,
] | None:
    if bar.open >= upper_price:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.OPEN_GAP_UP,
            "OUTCOME_RESOLVED",
        )
    if bar.open <= lower_price:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.OPEN_GAP_DOWN,
            "OUTCOME_RESOLVED",
        )
    upper_touched = bar.high >= upper_price
    lower_touched = bar.low <= lower_price
    if upper_touched and lower_touched:
        return (
            EntryPathObservationStatus.AMBIGUOUS,
            None,
            EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED,
            "DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED",
        )
    if upper_touched:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.INTRADAY_HIGH_ONLY,
            "OUTCOME_RESOLVED",
        )
    if lower_touched:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.INTRADAY_LOW_ONLY,
            "OUTCOME_RESOLVED",
        )
    return None


def _artifact_id(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
    observations: tuple[EntryPathObservation, ...],
) -> ArtifactId:
    payload = {
        "schema_version": "entry-path-materialization-v1",
        "target_id": str(contract.target_id),
        "source_dataset_ids": [str(value) for value in source_dataset_ids],
        "calendar_artifact_id": str(trading_calendar.artifact_id),
        "universe_id": str(population.universe_id),
        "decision_time": population.decision_time.isoformat(),
        "population_symbols": list(population.symbols),
        "population_source_dataset_ids": [
            str(value) for value in population.source_dataset_ids
        ],
        "materialized_at": materialized_at.isoformat(),
        "code_revision": code_revision,
        "config_hash": config_hash,
        "observations": [_observation_payload(value) for value in observations],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return ArtifactId(f"entry-path-materialization-{digest[:24]}")


def _observation_payload(value: EntryPathObservation) -> dict[str, object]:
    return {
        "symbol": value.symbol,
        "status": value.status.value,
        "outcome": value.outcome.value if value.outcome is not None else None,
        "reference_price": value.reference_price,
        "upper_price": value.upper_price,
        "lower_price": value.lower_price,
        "event_session_date": (
            value.event_session_date.isoformat()
            if value.event_session_date is not None
            else None
        ),
        "event_session_index": value.event_session_index,
        "trigger_type": (
            value.trigger_type.value if value.trigger_type is not None else None
        ),
        "evaluated_session_dates": [
            item.isoformat() for item in value.evaluated_session_dates
        ],
        "first_missing_session_date": (
            value.first_missing_session_date.isoformat()
            if value.first_missing_session_date is not None
            else None
        ),
        "reason_code": value.reason_code,
        "observed_at": (
            value.observed_at.isoformat() if value.observed_at is not None else None
        ),
    }


def _require_text(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"{label} must be a non-empty trimmed string")
