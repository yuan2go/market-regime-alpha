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
    RehearsalFuturePathCoverageAssertion,
    RehearsalFuturePathReadinessPolicy,
    RehearsalFutureSuspensionEvidence,
    TradingCalendarArtifact,
    TradingSession,
)
from market_regime_alpha.strategies.entry.contracts import (
    DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1,
    DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1,
    ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION,
    ENTRY_PATH_OBSERVATION_SCHEMA_VERSION,
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


def materialize_entry_path_target(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    entry_reference_evidence: tuple[RehearsalEntryReferenceEvidence, ...],
    future_daily_bars: tuple[RehearsalFutureDailyBar, ...],
    future_suspensions: tuple[RehearsalFutureSuspensionEvidence, ...],
    future_path_readiness_policy: RehearsalFuturePathReadinessPolicy,
    future_path_coverage_assertion: RehearsalFuturePathCoverageAssertion | None,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> EntryPathTargetMaterialization:
    """Materialize a Target without inferring basis, readiness, or coverage facts."""

    _validate_request(
        contract,
        population,
        source_dataset_ids,
        trading_calendar,
        materialized_at,
        code_revision,
        config_hash,
    )
    horizon_dates = trading_calendar.resolve_following_session_dates(
        population.decision_time,
        contract.spec.horizon_sessions,
    )
    source_ids = tuple(sorted(source_dataset_ids, key=str))
    sessions = {item.trade_date: item for item in trading_calendar.sessions}
    policy = future_path_readiness_policy
    readiness = _validate_readiness_policy(
        policy,
        source_ids,
        population,
        horizon_dates,
        sessions,
    )
    coverage = future_path_coverage_assertion
    _validate_coverage_assertion(
        coverage,
        policy,
        source_ids,
        population,
        sessions,
        materialized_at,
    )
    references = _index_references(
        entry_reference_evidence,
        population,
        source_ids,
        contract,
    )
    bars = _index_bars(
        future_daily_bars,
        set(population.symbols),
        horizon_dates,
        sessions,
        materialized_at,
        source_ids,
        policy.source_dataset_id,
        contract,
        references,
    )
    suspensions = _index_suspensions(
        future_suspensions,
        set(population.symbols),
        horizon_dates,
        sessions,
        materialized_at,
        source_ids,
        policy.source_dataset_id,
    )
    for key, evidence in suspensions.items():
        if evidence.is_suspended and key in bars:
            raise ValueError("confirmed suspension conflicts with future daily bar evidence")

    observations: list[EntryPathObservation] = []
    bar_ids: list[ArtifactId] = []
    suspension_ids: list[ArtifactId] = []
    coverage_was_consumed = False
    for symbol in population.symbols:
        observation, used_bars, used_suspensions, symbol_used_coverage = _evaluate_symbol(
            symbol,
            contract,
            references[symbol],
            horizon_dates,
            sessions,
            readiness,
            coverage,
            bars,
            suspensions,
            materialized_at,
        )
        observations.append(observation)
        bar_ids.extend(used_bars)
        suspension_ids.extend(used_suspensions)
        coverage_was_consumed = coverage_was_consumed or symbol_used_coverage

    reference_ids = tuple(
        sorted((evidence.evidence_id for evidence in references.values()), key=str)
    )
    ordered_bars = tuple(sorted(set(bar_ids), key=str))
    ordered_suspensions = tuple(sorted(set(suspension_ids), key=str))
    consumed_coverage_id = (
        coverage.evidence_id
        if coverage is not None and coverage_was_consumed
        else None
    )
    values = tuple(observations)
    artifact_id = _artifact_id(
        contract,
        population,
        source_ids,
        trading_calendar,
        materialized_at,
        code_revision,
        config_hash,
        policy.policy_id,
        consumed_coverage_id,
        reference_ids,
        ordered_bars,
        ordered_suspensions,
        values,
    )
    return EntryPathTargetMaterialization(
        artifact_id=artifact_id,
        target_id=contract.target_id,
        source_dataset_ids=source_ids,
        calendar_artifact_id=trading_calendar.artifact_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        schema_version=ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION,
        observation_schema_version=ENTRY_PATH_OBSERVATION_SCHEMA_VERSION,
        readiness_policy_id=policy.policy_id,
        consumed_coverage_assertion_id=consumed_coverage_id,
        entry_reference_evidence_ids=reference_ids,
        consumed_future_bar_evidence_ids=ordered_bars,
        consumed_future_suspension_evidence_ids=ordered_suspensions,
        observations=values,
    )


def _validate_request(
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    calendar: TradingCalendarArtifact,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> None:
    if not isinstance(contract, EntryPathTargetContract) or not isinstance(
        population,
        CandidatePopulation,
    ):
        raise TypeError("contract and population must use their canonical contracts")
    if not isinstance(calendar, TradingCalendarArtifact) or not isinstance(
        materialized_at,
        AsOfTime,
    ):
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
    if not all(
        isinstance(value, str) and value.strip() == value and value
        for value in (code_revision, config_hash)
    ):
        raise ValueError("code_revision and config_hash must be non-empty trimmed strings")
    spec = contract.spec
    if not (
        spec.schema_version == ENTRY_PATH_TARGET_SCHEMA_VERSION
        and spec.target_start_convention
        == NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
        and spec.reference_price_convention
        == DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1
        and spec.path_ordering_convention
        == DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1
    ):
        raise ValueError("Entry path materializer supports only the approved V1 conventions")


def _validate_readiness_policy(
    policy: RehearsalFuturePathReadinessPolicy,
    source_ids: tuple[DatasetId, ...],
    population: CandidatePopulation,
    horizon: tuple[date, ...],
    sessions: dict[date, TradingSession],
) -> dict[date, AvailabilityTime]:
    if not isinstance(policy, RehearsalFuturePathReadinessPolicy):
        raise TypeError("future_path_readiness_policy must be a readiness policy")
    if policy.source_dataset_id not in source_ids:
        raise ValueError("readiness policy source Dataset is not declared")
    if policy.effective_at.value > population.decision_time.value:
        raise ValueError("readiness policy effective_at must not follow Decision Time")
    dates = tuple(item.session_date for item in policy.session_readiness)
    if dates != horizon:
        raise ValueError("readiness policy must exactly cover Target horizon")
    readiness: dict[date, AvailabilityTime] = {}
    for item in policy.session_readiness:
        session = sessions.get(item.session_date)
        if session is None:
            raise ValueError("readiness session date is off-Calendar")
        if item.evidence_ready_at.value < session.session_close:
            raise ValueError("readiness deadline is before TradingSession close")
        readiness[item.session_date] = item.evidence_ready_at
    return readiness


def _validate_coverage_assertion(
    coverage: RehearsalFuturePathCoverageAssertion | None,
    policy: RehearsalFuturePathReadinessPolicy,
    source_ids: tuple[DatasetId, ...],
    population: CandidatePopulation,
    sessions: dict[date, TradingSession],
    materialized_at: AsOfTime,
) -> None:
    if coverage is None:
        return
    if not isinstance(coverage, RehearsalFuturePathCoverageAssertion):
        raise TypeError("future_path_coverage_assertion must be a coverage assertion or None")
    if coverage.source_dataset_id not in source_ids:
        raise ValueError("coverage assertion source Dataset is not declared")
    if coverage.source_dataset_id != policy.source_dataset_id:
        raise ValueError("coverage assertion source Dataset conflicts with readiness policy")
    if coverage.available_at.value > materialized_at.value:
        raise ValueError("coverage assertion is available after materialized_at")
    if coverage.covered_symbols != population.symbols:
        raise ValueError("coverage assertion covered_symbols must exactly equal Candidate Population")
    watermark_session = sessions.get(coverage.coverage_through_session_date)
    if watermark_session is None:
        raise ValueError("coverage watermark session date is off-Calendar")
    if coverage.available_at.value < watermark_session.session_close:
        raise ValueError("coverage assertion available_at is before watermark session close")


def _index_references(
    values: tuple[RehearsalEntryReferenceEvidence, ...],
    population: CandidatePopulation,
    source_ids: tuple[DatasetId, ...],
    contract: EntryPathTargetContract,
) -> dict[str, RehearsalEntryReferenceEvidence]:
    indexed: dict[str, RehearsalEntryReferenceEvidence] = {}
    for evidence in values:
        if not isinstance(evidence, RehearsalEntryReferenceEvidence):
            raise TypeError("entry_reference_evidence must contain Entry reference evidence")
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


def _index_bars(
    values: tuple[RehearsalFutureDailyBar, ...],
    symbols: set[str],
    horizon: tuple[date, ...],
    sessions: dict[date, TradingSession],
    materialized_at: AsOfTime,
    source_ids: tuple[DatasetId, ...],
    future_source_id: DatasetId,
    contract: EntryPathTargetContract,
    references: dict[str, RehearsalEntryReferenceEvidence],
) -> dict[tuple[str, date], RehearsalFutureDailyBar]:
    indexed: dict[tuple[str, date], RehearsalFutureDailyBar] = {}
    for bar in values:
        if not isinstance(bar, RehearsalFutureDailyBar):
            raise TypeError("future_daily_bars must contain RehearsalFutureDailyBar")
        _validate_future_scope(bar.symbol, bar.session_date, symbols, horizon, sessions)
        key = (bar.symbol, bar.session_date)
        if key in indexed:
            raise ValueError("duplicate future daily bar")
        if bar.source_dataset_id not in source_ids or bar.source_dataset_id != future_source_id:
            raise ValueError("future daily bar source Dataset conflicts with readiness policy")
        if (
            bar.price_adjustment_basis != contract.spec.price_adjustment_basis
            or bar.price_adjustment_basis
            != references[bar.symbol].price_adjustment_basis
        ):
            raise ValueError("future daily bar price adjustment basis mismatch")
        _validate_future_time(
            "future daily bar",
            sessions[bar.session_date].session_close,
            bar.finalized_at.value,
            bar.available_at.value,
            materialized_at,
        )
        indexed[key] = bar
    return indexed


def _index_suspensions(
    values: tuple[RehearsalFutureSuspensionEvidence, ...],
    symbols: set[str],
    horizon: tuple[date, ...],
    sessions: dict[date, TradingSession],
    materialized_at: AsOfTime,
    source_ids: tuple[DatasetId, ...],
    future_source_id: DatasetId,
) -> dict[tuple[str, date], RehearsalFutureSuspensionEvidence]:
    indexed: dict[tuple[str, date], RehearsalFutureSuspensionEvidence] = {}
    for evidence in values:
        if not isinstance(evidence, RehearsalFutureSuspensionEvidence):
            raise TypeError(
                "future_suspensions must contain RehearsalFutureSuspensionEvidence"
            )
        _validate_future_scope(
            evidence.symbol,
            evidence.session_date,
            symbols,
            horizon,
            sessions,
        )
        key = (evidence.symbol, evidence.session_date)
        if key in indexed:
            raise ValueError("duplicate future suspension evidence")
        if (
            evidence.source_dataset_id not in source_ids
            or evidence.source_dataset_id != future_source_id
        ):
            raise ValueError(
                "future suspension source Dataset conflicts with readiness policy"
            )
        _validate_future_time(
            "future suspension evidence",
            sessions[evidence.session_date].session_close,
            evidence.finalized_at.value,
            evidence.available_at.value,
            materialized_at,
        )
        indexed[key] = evidence
    return indexed


def _validate_future_scope(
    symbol: str,
    session_date: date,
    symbols: set[str],
    horizon: tuple[date, ...],
    sessions: dict[date, TradingSession],
) -> None:
    if symbol not in symbols:
        raise ValueError("future evidence symbol is outside Candidate Population")
    if session_date not in sessions:
        raise ValueError("future evidence session date is off-Calendar")
    if session_date not in horizon:
        raise ValueError("future evidence is outside resolved Target horizon")


def _validate_future_time(
    label: str,
    close: datetime,
    finalized_at: datetime,
    available_at: datetime,
    materialized_at: AsOfTime,
) -> None:
    if finalized_at < close:
        raise ValueError(f"{label} finalized before TradingSession close")
    if available_at > materialized_at.value:
        raise ValueError(f"{label} is available after materialized_at")


def _evaluate_symbol(
    symbol: str,
    contract: EntryPathTargetContract,
    reference: RehearsalEntryReferenceEvidence,
    horizon: tuple[date, ...],
    sessions: dict[date, TradingSession],
    readiness: dict[date, AvailabilityTime],
    coverage: RehearsalFuturePathCoverageAssertion | None,
    bars: dict[tuple[str, date], RehearsalFutureDailyBar],
    suspensions: dict[tuple[str, date], RehearsalFutureSuspensionEvidence],
    materialized_at: AsOfTime,
) -> tuple[EntryPathObservation, tuple[ArtifactId, ...], tuple[ArtifactId, ...], bool]:
    reference_price = float(reference.reference_price)
    upper = reference_price * (1.0 + contract.spec.upper_return)
    lower = reference_price * (1.0 + contract.spec.lower_return)
    evaluated: list[date] = []
    used_bars: list[ArtifactId] = []
    used_suspensions: list[ArtifactId] = []
    latest: AvailabilityTime | None = None
    for index, session_date in enumerate(horizon, start=1):
        if materialized_at.value < sessions[session_date].session_close:
            return (
                _pending(
                    symbol,
                    reference_price,
                    upper,
                    lower,
                    evaluated,
                    EntryPathReasonCode.HORIZON_NOT_COMPLETE,
                ),
                tuple(used_bars),
                tuple(used_suspensions),
                False,
            )

        key = (symbol, session_date)
        bar = bars.get(key)
        if bar is not None:
            evaluated.append(session_date)
            used_bars.append(bar.evidence_id)
            latest = bar.available_at
            resolved = _classify_bar(bar, upper, lower)
            if resolved is not None:
                status, outcome, trigger, reason = resolved
                return (
                    EntryPathObservation(
                        symbol=symbol,
                        status=status,
                        outcome=outcome,
                        reference_price=reference_price,
                        upper_price=upper,
                        lower_price=lower,
                        event_session_date=session_date,
                        event_session_index=index,
                        trigger_type=trigger,
                        evaluated_session_dates=tuple(evaluated),
                        first_missing_session_date=None,
                        reason_code=reason,
                        observed_at=bar.available_at,
                    ),
                    tuple(used_bars),
                    tuple(used_suspensions),
                    False,
                )
            continue

        suspension = suspensions.get(key)
        if suspension is not None and suspension.is_suspended:
            evaluated.append(session_date)
            used_suspensions.append(suspension.evidence_id)
            latest = suspension.available_at
            continue

        if materialized_at.value < readiness[session_date].value:
            return (
                _pending(
                    symbol,
                    reference_price,
                    upper,
                    lower,
                    evaluated,
                    EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE,
                ),
                tuple(used_bars),
                tuple(used_suspensions),
                False,
            )
        if coverage is None or coverage.coverage_through_session_date < session_date:
            return (
                _pending(
                    symbol,
                    reference_price,
                    upper,
                    lower,
                    evaluated,
                    EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE,
                ),
                tuple(used_bars),
                tuple(used_suspensions),
                coverage is not None,
            )
        return (
            EntryPathObservation(
                symbol=symbol,
                status=EntryPathObservationStatus.MISSING,
                outcome=None,
                reference_price=reference_price,
                upper_price=upper,
                lower_price=lower,
                event_session_date=None,
                event_session_index=None,
                trigger_type=None,
                evaluated_session_dates=tuple(evaluated),
                first_missing_session_date=session_date,
                reason_code=EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING,
                observed_at=coverage.available_at,
            ),
            tuple(used_bars),
            tuple(used_suspensions),
            True,
        )

    assert latest is not None
    return (
        EntryPathObservation(
            symbol=symbol,
            status=EntryPathObservationStatus.AVAILABLE,
            outcome=EntryPathOutcome.TIMEOUT,
            reference_price=reference_price,
            upper_price=upper,
            lower_price=lower,
            event_session_date=horizon[-1],
            event_session_index=len(horizon),
            trigger_type=EntryPathTriggerType.HORIZON_EXHAUSTED,
            evaluated_session_dates=tuple(evaluated),
            first_missing_session_date=None,
            reason_code=EntryPathReasonCode.HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH,
            observed_at=latest,
        ),
        tuple(used_bars),
        tuple(used_suspensions),
        False,
    )


def _pending(
    symbol: str,
    reference: float,
    upper: float,
    lower: float,
    evaluated: list[date],
    reason: EntryPathReasonCode,
) -> EntryPathObservation:
    return EntryPathObservation(
        symbol=symbol,
        status=EntryPathObservationStatus.NOT_YET_OBSERVED,
        outcome=None,
        reference_price=reference,
        upper_price=upper,
        lower_price=lower,
        event_session_date=None,
        event_session_index=None,
        trigger_type=None,
        evaluated_session_dates=tuple(evaluated),
        first_missing_session_date=None,
        reason_code=reason,
        observed_at=None,
    )


def _classify_bar(
    bar: RehearsalFutureDailyBar,
    upper: float,
    lower: float,
) -> tuple[
    EntryPathObservationStatus,
    EntryPathOutcome | None,
    EntryPathTriggerType,
    EntryPathReasonCode,
] | None:
    if bar.open >= upper:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.OPEN_GAP_UP,
            EntryPathReasonCode.OUTCOME_RESOLVED,
        )
    if bar.open <= lower:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.OPEN_GAP_DOWN,
            EntryPathReasonCode.OUTCOME_RESOLVED,
        )
    if bar.high >= upper and bar.low <= lower:
        return (
            EntryPathObservationStatus.AMBIGUOUS,
            None,
            EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED,
            EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED,
        )
    if bar.high >= upper:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.UP_FIRST,
            EntryPathTriggerType.INTRADAY_HIGH_ONLY,
            EntryPathReasonCode.OUTCOME_RESOLVED,
        )
    if bar.low <= lower:
        return (
            EntryPathObservationStatus.AVAILABLE,
            EntryPathOutcome.DOWN_FIRST,
            EntryPathTriggerType.INTRADAY_LOW_ONLY,
            EntryPathReasonCode.OUTCOME_RESOLVED,
        )
    return None


def _artifact_id(
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    sources: tuple[DatasetId, ...],
    calendar: TradingCalendarArtifact,
    materialized_at: AsOfTime,
    revision: str,
    config: str,
    readiness_policy_id: ArtifactId,
    consumed_coverage_assertion_id: ArtifactId | None,
    references: tuple[ArtifactId, ...],
    bars: tuple[ArtifactId, ...],
    suspensions: tuple[ArtifactId, ...],
    observations: tuple[EntryPathObservation, ...],
) -> ArtifactId:
    payload = {
        "schema_version": ENTRY_PATH_MATERIALIZATION_SCHEMA_VERSION,
        "observation_schema_version": ENTRY_PATH_OBSERVATION_SCHEMA_VERSION,
        "target_id": str(contract.target_id),
        "source_dataset_ids": [str(value) for value in sources],
        "calendar_artifact_id": str(calendar.artifact_id),
        "universe_id": str(population.universe_id),
        "decision_time": population.decision_time.isoformat(),
        "population_symbols": list(population.symbols),
        "materialized_at": materialized_at.isoformat(),
        "code_revision": revision,
        "config_hash": config,
        "readiness_policy_id": str(readiness_policy_id),
        "consumed_coverage_assertion_id": (
            str(consumed_coverage_assertion_id)
            if consumed_coverage_assertion_id is not None
            else None
        ),
        "entry_reference_evidence_ids": [str(value) for value in references],
        "consumed_future_bar_evidence_ids": [str(value) for value in bars],
        "consumed_future_suspension_evidence_ids": [str(value) for value in suspensions],
        "observations": [_observation_payload(value) for value in observations],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return ArtifactId(
        f"entry-path-materialization-{sha256(canonical.encode('utf-8')).hexdigest()[:24]}"
    )


def _observation_payload(value: EntryPathObservation) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "symbol": value.symbol,
        "status": value.status.value,
        "outcome": value.outcome.value if value.outcome else None,
        "reference_price": value.reference_price,
        "upper_price": value.upper_price,
        "lower_price": value.lower_price,
        "event_session_date": (
            value.event_session_date.isoformat() if value.event_session_date else None
        ),
        "event_session_index": value.event_session_index,
        "trigger_type": value.trigger_type.value if value.trigger_type else None,
        "evaluated_session_dates": [
            item.isoformat() for item in value.evaluated_session_dates
        ],
        "first_missing_session_date": (
            value.first_missing_session_date.isoformat()
            if value.first_missing_session_date
            else None
        ),
        "reason_code": value.reason_code.value,
        "observed_at": value.observed_at.isoformat() if value.observed_at else None,
    }
