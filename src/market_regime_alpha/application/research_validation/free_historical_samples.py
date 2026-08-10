"""Free-data historical samples for the exploratory PathForecast Registry.

The builder deliberately treats a retrospective BaoStock retrieval as available
only at retrieval time.  It therefore cannot manufacture PIT or OOS status, and
it never substitutes a daily close for the required 14:55 decision reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable, Mapping, Protocol
from zoneinfo import ZoneInfo

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
    OutcomeTargetProtocol,
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.core.identity import ArtifactId, TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data_sources.a_share_bars import AShareBarProvider
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastConfig,
    PathForecastSample,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryPathObservationStatus,
    EntryPathReasonCode,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_DECISION_BAR_TIME = time(14, 55)
_CHECKPOINT_BAR_TIMES: Mapping[OutcomeCheckpoint, time] = {
    OutcomeCheckpoint.OPEN: time(9, 35),
    OutcomeCheckpoint.TIME_0945: time(9, 45),
    OutcomeCheckpoint.TIME_1000: time(10, 0),
    OutcomeCheckpoint.TIME_1030: time(10, 30),
    OutcomeCheckpoint.TIME_1130: time(11, 30),
    OutcomeCheckpoint.CLOSE: time(15, 0),
}
FREE_HISTORICAL_REGISTRY_VERSION = "baostock-free-data-exploratory-v1"
FREE_HISTORICAL_LIMITATIONS = (
    "ALPHA_VALIDATED_FALSE",
    "BACKFILLED_RETRIEVAL_NOT_POINT_IN_TIME",
    "ENTRY_QUALIFIED_FALSE",
    "FORMAL_OOS_FALSE",
    "FORMAL_PIT_FALSE",
    "FREE_DATA_EXPLORATORY",
    "NO_TRADING_AUTHORITY",
    "PRODUCTION_AUTHORIZED_FALSE",
    "SESSION_SEQUENCE_FROM_OBSERVED_SYMBOL_BARS",
    "UNQUALIFIED",
)


@dataclass(frozen=True, slots=True)
class FreeHistoricalBar:
    symbol: str
    observed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Free historical bar timestamp must be timezone-aware")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("Free historical bar prices must be positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Free historical bar OHLC ordering is invalid")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "observed_at": timestamp(self.observed_at),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
        }


class FreeHistoricalBarReader(Protocol):
    provider_id: str
    price_adjustment_basis: str

    def read(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[FreeHistoricalBar, ...]: ...


class HistoricalSampleDatasetWriter(Protocol):
    def record_sample_dataset(self, dataset: HistoricalSampleDataset) -> None: ...

    def record_free_historical_pipeline(
        self,
        *,
        decisions: tuple[FreeHistoricalDecision, ...],
        outcomes: tuple[FreeHistoricalMultiHorizonOutcome, ...],
        dataset: HistoricalSampleDataset,
    ) -> None: ...

    def find_sample_dataset(
        self,
        *,
        registry_version: str,
        target_id: TargetId,
    ) -> HistoricalSampleDataset | None: ...


class AShareBarProviderReader:
    """Adapter over the existing normalized BaoStock five-minute provider."""

    provider_id = "BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS_5MIN_ADJUSTFLAG_3"
    price_adjustment_basis = "RAW_UNADJUSTED_TRADABLE_PRICE_V1"

    def __init__(self, provider: AShareBarProvider) -> None:
        self._provider = provider

    def read(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[FreeHistoricalBar, ...]:
        frame = self._provider.minute_bars(
            symbol,
            freq="5min",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        required = {"symbol", "timestamp", "open", "high", "low", "close"}
        if not required.issubset(getattr(frame, "columns", ())):
            raise ValueError("BaoStock historical frame omits required normalized columns")
        bars = []
        for row in frame.sort_values("timestamp").to_dict(orient="records"):
            observed = row["timestamp"]
            if hasattr(observed, "to_pydatetime"):
                observed = observed.to_pydatetime()
            if not isinstance(observed, datetime):
                observed = datetime.fromisoformat(str(observed))
            if observed.tzinfo is None or observed.utcoffset() is None:
                observed = observed.replace(tzinfo=_SHANGHAI)
            bars.append(
                FreeHistoricalBar(
                    symbol=str(row["symbol"]),
                    observed_at=observed.astimezone(_SHANGHAI),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                )
            )
        return tuple(bars)


@dataclass(frozen=True, slots=True)
class FreeHistoricalDecision:
    decision_id: ArtifactId
    decision_hash: str
    symbol: str
    decision_time: datetime
    reference_price: Decimal
    source_provider_id: str
    retrieved_at: datetime
    limitations: tuple[str, ...] = FREE_HISTORICAL_LIMITATIONS

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        decision_time: datetime,
        reference_price: Decimal,
        source_provider_id: str,
        retrieved_at: datetime,
    ) -> FreeHistoricalDecision:
        values = {
            "schema": "free-historical-decision/v1",
            "symbol": symbol,
            "decision_time": timestamp(decision_time),
            "reference_price": str(reference_price),
            "source_provider_id": source_provider_id,
            "retrieved_at": timestamp(retrieved_at),
            "limitations": list(FREE_HISTORICAL_LIMITATIONS),
        }
        artifact_id, digest = content_identity("free-historical-decision", values)
        return cls(
            artifact_id,
            digest,
            symbol,
            decision_time,
            reference_price,
            source_provider_id,
            retrieved_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "free-historical-decision/v1",
            "symbol": self.symbol,
            "decision_time": timestamp(self.decision_time),
            "reference_price": str(self.reference_price),
            "source_provider_id": self.source_provider_id,
            "retrieved_at": timestamp(self.retrieved_at),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class FreeHistoricalMultiHorizonOutcome:
    outcome_id: ArtifactId
    outcome_hash: str
    decision_reference: ValidationArtifactReference
    next_session_date: date
    checkpoint_prices: tuple[tuple[str, Decimal], ...]
    path_session_ohlc: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...]
    target_protocol_id: ArtifactId
    target_protocol_hash: str
    retrieved_at: datetime
    limitations: tuple[str, ...] = FREE_HISTORICAL_LIMITATIONS

    @classmethod
    def create(
        cls,
        *,
        decision: FreeHistoricalDecision,
        next_session_date: date,
        checkpoint_prices: tuple[tuple[str, Decimal], ...],
        path_session_ohlc: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...],
        target_protocol: OutcomeTargetProtocol,
        retrieved_at: datetime,
    ) -> FreeHistoricalMultiHorizonOutcome:
        decision_reference = ValidationArtifactReference(
            "FREE_HISTORICAL_DECISION",
            decision.decision_id,
            decision.decision_hash,
        )
        values = _outcome_payload(
            decision_reference=decision_reference,
            next_session_date=next_session_date,
            checkpoint_prices=checkpoint_prices,
            path_session_ohlc=path_session_ohlc,
            target_protocol=target_protocol,
            retrieved_at=retrieved_at,
        )
        artifact_id, digest = content_identity("free-historical-multi-horizon-outcome", values)
        return cls(
            artifact_id,
            digest,
            decision_reference,
            next_session_date,
            checkpoint_prices,
            path_session_ohlc,
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
            retrieved_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": str(self.outcome_id),
            "outcome_hash": self.outcome_hash,
            **self.identity_payload(),
        }

    def identity_payload(self) -> dict[str, Any]:
        return _outcome_payload(
            decision_reference=self.decision_reference,
            next_session_date=self.next_session_date,
            checkpoint_prices=self.checkpoint_prices,
            path_session_ohlc=self.path_session_ohlc,
            target_protocol=_ProtocolIdentity(
                self.target_protocol_id,
                self.target_protocol_hash,
            ),
            retrieved_at=self.retrieved_at,
        )


@dataclass(frozen=True, slots=True)
class FreeHistoricalSampleBuildResult:
    dataset: HistoricalSampleDataset | None
    decisions: tuple[FreeHistoricalDecision, ...]
    outcomes: tuple[FreeHistoricalMultiHorizonOutcome, ...]
    provider_failures: tuple[tuple[str, str], ...]
    skipped_symbols: tuple[str, ...]
    reused_registry: bool

    @property
    def sample_count(self) -> int:
        return 0 if self.dataset is None else len(self.dataset.records)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": None if self.dataset is None else str(self.dataset.dataset_id),
            "dataset_hash": None if self.dataset is None else self.dataset.dataset_hash,
            "sample_count": self.sample_count,
            "qualification": "UNQUALIFIED",
            "evidence_class": "FREE_DATA_EXPLORATORY",
            "decision_count": len(self.decisions),
            "outcome_count": len(self.outcomes),
            "provider_failures": [list(item) for item in self.provider_failures],
            "skipped_symbols": list(self.skipped_symbols),
            "reused_registry": self.reused_registry,
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class _ProtocolIdentity:
    protocol_id: ArtifactId
    protocol_hash: str


class FreeHistoricalSamplePipeline:
    """Build and register only retrospective, UNQUALIFIED free-data samples."""

    def __init__(
        self,
        *,
        reader: FreeHistoricalBarReader,
        repository: HistoricalSampleDatasetWriter,
        clock: Callable[[], datetime],
        lookback_calendar_days: int = 180,
        maximum_samples_per_symbol: int = 60,
    ) -> None:
        if lookback_calendar_days <= 0 or maximum_samples_per_symbol <= 0:
            raise ValueError("Historical sample lookback bounds must be positive")
        self._reader = reader
        self._repository = repository
        self._clock = clock
        self._lookback_calendar_days = lookback_calendar_days
        self._maximum_samples_per_symbol = maximum_samples_per_symbol

    def build_and_register(
        self,
        *,
        symbols: tuple[str, ...],
        configuration: PathForecastConfig,
        current_decision_time: DecisionTime,
    ) -> FreeHistoricalSampleBuildResult:
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical sample symbols must be non-empty, unique and sorted")
        if (
            configuration.target_contract.spec.price_adjustment_basis
            != self._reader.price_adjustment_basis
        ):
            raise ValueError(
                "Historical sample Target price adjustment basis does not match "
                "the free-data Reader"
            )
        retrieved_at = self._clock().astimezone(UTC).replace(microsecond=0)
        current_date = current_decision_time.value.astimezone(_SHANGHAI).date()
        end_date = current_date - timedelta(days=1)
        start_date = end_date - timedelta(days=self._lookback_calendar_days)
        protocol = engineering_multi_horizon_protocol()
        decisions: list[FreeHistoricalDecision] = []
        outcomes: list[FreeHistoricalMultiHorizonOutcome] = []
        records: list[HistoricalPathSampleRecord] = []
        failures: list[tuple[str, str]] = []
        skipped: list[str] = []
        target_reference = ValidationArtifactReference(
            "ENTRY_PATH_TARGET",
            ArtifactId(str(configuration.target_contract.target_id)),
            canonical_hash(configuration.to_canonical_dict()["target_contract"]),
        )
        scope_hash = canonical_hash(
            {
                "symbols": list(symbols),
                "target_id": str(configuration.target_contract.target_id),
                "current_decision_date": current_date.isoformat(),
            }
        ).split(":", 1)[1][:16]
        registry_version = (
            f"{FREE_HISTORICAL_REGISTRY_VERSION}:{current_date.isoformat()}:{scope_hash}"
        )
        existing = self._repository.find_sample_dataset(
            registry_version=registry_version,
            target_id=configuration.target_contract.target_id,
        )
        if existing is not None and {
            item.sample.symbol for item in existing.records
        } == set(symbols):
            return FreeHistoricalSampleBuildResult(
                existing,
                (),
                (),
                (),
                (),
                True,
            )
        for symbol in symbols:
            try:
                bars = self._reader.read(symbol=symbol, start_date=start_date, end_date=end_date)
                symbol_records = _build_symbol_records(
                    symbol=symbol,
                    bars=bars,
                    configuration=configuration,
                    target_reference=target_reference,
                    target_protocol=protocol,
                    provider_id=self._reader.provider_id,
                    retrieved_at=retrieved_at,
                    maximum_samples=self._maximum_samples_per_symbol,
                )
            except Exception as exc:  # noqa: BLE001 - provider clients expose mixed failures.
                failures.append((symbol, type(exc).__name__))
                continue
            if not symbol_records:
                skipped.append(symbol)
                continue
            for decision, outcome, record in symbol_records:
                decisions.append(decision)
                outcomes.append(outcome)
                records.append(record)
        if not records:
            return FreeHistoricalSampleBuildResult(
                None,
                tuple(decisions),
                tuple(outcomes),
                tuple(sorted(failures)),
                tuple(sorted(skipped)),
                False,
            )
        refreshed_symbols = {item.sample.symbol for item in records}
        if existing is not None:
            records.extend(
                item
                for item in existing.records
                if item.sample.symbol not in refreshed_symbols
            )
            retrieved_at = max(retrieved_at, existing.available_at)
        dataset = HistoricalSampleDataset.create(
            registry_version=registry_version,
            target_reference=target_reference,
            records=tuple(records),
            available_at=retrieved_at,
        )
        self._repository.record_free_historical_pipeline(
            decisions=tuple(decisions),
            outcomes=tuple(outcomes),
            dataset=dataset,
        )
        return FreeHistoricalSampleBuildResult(
            dataset,
            tuple(sorted(decisions, key=lambda item: (item.decision_time, item.symbol))),
            tuple(sorted(outcomes, key=lambda item: (item.next_session_date, str(item.outcome_id)))),
            tuple(sorted(failures)),
            tuple(sorted(skipped)),
            False,
        )


def _build_symbol_records(
    *,
    symbol: str,
    bars: tuple[FreeHistoricalBar, ...],
    configuration: PathForecastConfig,
    target_reference: ValidationArtifactReference,
    target_protocol: OutcomeTargetProtocol,
    provider_id: str,
    retrieved_at: datetime,
    maximum_samples: int,
) -> tuple[tuple[FreeHistoricalDecision, FreeHistoricalMultiHorizonOutcome, HistoricalPathSampleRecord], ...]:
    by_session: dict[date, tuple[FreeHistoricalBar, ...]] = {}
    for bar in bars:
        if bar.symbol != symbol:
            raise ValueError("Historical provider returned a symbol outside its request")
        local = bar.observed_at.astimezone(_SHANGHAI)
        by_session[local.date()] = (*by_session.get(local.date(), ()), bar)
    sessions = tuple(sorted(by_session))
    horizon = configuration.target_contract.spec.horizon_sessions
    candidates = sessions[: -horizon] if len(sessions) > horizon else ()
    selected = candidates[-maximum_samples:]
    output = []
    for decision_date in selected:
        decision_bars = tuple(sorted(by_session[decision_date], key=lambda item: item.observed_at))
        reference_bar = next(
            (
                item
                for item in decision_bars
                if item.observed_at.astimezone(_SHANGHAI).time().replace(tzinfo=None) == _DECISION_BAR_TIME
            ),
            None,
        )
        if reference_bar is None:
            continue
        decision_index = sessions.index(decision_date)
        path_dates = sessions[decision_index + 1 : decision_index + 1 + horizon]
        if len(path_dates) != horizon:
            continue
        decision = FreeHistoricalDecision.create(
            symbol=symbol,
            decision_time=datetime.combine(decision_date, _DECISION_BAR_TIME, tzinfo=_SHANGHAI),
            reference_price=reference_bar.close,
            source_provider_id=provider_id,
            retrieved_at=retrieved_at,
        )
        path_ohlc = tuple(_session_ohlc(session_date, by_session[session_date]) for session_date in path_dates)
        next_bars = tuple(sorted(by_session[path_dates[0]], key=lambda item: item.observed_at))
        checkpoints = _checkpoint_prices(next_bars)
        if checkpoints is None:
            continue
        outcome = FreeHistoricalMultiHorizonOutcome.create(
            decision=decision,
            next_session_date=path_dates[0],
            checkpoint_prices=checkpoints,
            path_session_ohlc=path_ohlc,
            target_protocol=target_protocol,
            retrieved_at=retrieved_at,
        )
        status, reason, mfe, mae, realized = _path_metrics(
            reference_price=decision.reference_price,
            path_session_ohlc=path_ohlc,
            upper_return=Decimal(str(configuration.target_contract.spec.upper_return)),
            lower_return=Decimal(str(configuration.target_contract.spec.lower_return)),
        )
        sample_values = {
            "source_artifact_id": str(outcome.outcome_id),
            "source_content_hash": outcome.outcome_hash,
            "symbol": symbol,
            "target_id": str(configuration.target_contract.target_id),
            "sample_decision_time": timestamp(decision.decision_time),
            "available_at": timestamp(retrieved_at),
            "observation_status": status.value,
            "observation_reason_code": reason.value,
            "realized_mfe": mfe,
            "realized_mae": mae,
            "realized_return": realized,
            "schema_version": PATH_FORECAST_SAMPLE_SCHEMA,
        }
        sample_id, _ = content_identity("path-forecast-sample", sample_values)
        sample = PathForecastSample(
            sample_id=sample_id,
            source_artifact_id=outcome.outcome_id,
            source_content_hash=outcome.outcome_hash,
            symbol=symbol,
            target_id=configuration.target_contract.target_id,
            sample_decision_time=DecisionTime(decision.decision_time),
            available_at=AvailabilityTime(retrieved_at),
            observation_status=status,
            observation_reason_code=reason,
            realized_mfe=mfe,
            realized_mae=mae,
            realized_return=realized,
            schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
        )
        record = HistoricalPathSampleRecord.register_unqualified(
            sample=sample,
            target_reference=target_reference,
            outcome_reference=ValidationArtifactReference(
                "FREE_HISTORICAL_MULTI_HORIZON_OUTCOME",
                outcome.outcome_id,
                outcome.outcome_hash,
            ),
            pit_lineage=(
                ValidationArtifactReference(
                    "FREE_HISTORICAL_DECISION",
                    decision.decision_id,
                    decision.decision_hash,
                ),
            ),
            registered_at=retrieved_at,
            reason_codes=(
                "BACKFILLED_RETRIEVAL_NOT_POINT_IN_TIME",
                "FORMAL_OOS_FALSE",
                "FORMAL_PIT_FALSE",
                "FREE_DATA_EXPLORATORY",
                "UNQUALIFIED",
            ),
        )
        output.append((decision, outcome, record))
    return tuple(output)


def _checkpoint_prices(bars: tuple[FreeHistoricalBar, ...]) -> tuple[tuple[str, Decimal], ...] | None:
    indexed = {
        item.observed_at.astimezone(_SHANGHAI).time().replace(tzinfo=None): item
        for item in bars
    }
    values = []
    for checkpoint, bar_time in _CHECKPOINT_BAR_TIMES.items():
        bar = indexed.get(bar_time)
        if bar is None:
            return None
        price = bar.open if checkpoint is OutcomeCheckpoint.OPEN else bar.close
        values.append((checkpoint.value, price))
    return tuple(sorted(values))


def _session_ohlc(
    session_date: date,
    bars: tuple[FreeHistoricalBar, ...],
) -> tuple[str, Decimal, Decimal, Decimal, Decimal]:
    ordered = tuple(sorted(bars, key=lambda item: item.observed_at))
    if not ordered:
        raise ValueError("Historical session cannot be empty")
    return (
        session_date.isoformat(),
        ordered[0].open,
        max(item.high for item in ordered),
        min(item.low for item in ordered),
        ordered[-1].close,
    )


def _path_metrics(
    *,
    reference_price: Decimal,
    path_session_ohlc: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...],
    upper_return: Decimal,
    lower_return: Decimal,
) -> tuple[EntryPathObservationStatus, EntryPathReasonCode, float | None, float | None, float | None]:
    upper = reference_price * (Decimal("1") + upper_return)
    lower = reference_price * (Decimal("1") + lower_return)
    for _, open_price, high, low, _ in path_session_ohlc:
        if open_price >= upper or open_price <= lower:
            break
        if high >= upper and low <= lower:
            return (
                EntryPathObservationStatus.AMBIGUOUS,
                EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED,
                None,
                None,
                None,
            )
        if high >= upper or low <= lower:
            break
    high = max(item[2] for item in path_session_ohlc)
    low = min(item[3] for item in path_session_ohlc)
    close = path_session_ohlc[-1][4]
    touched = high >= upper or low <= lower
    return (
        EntryPathObservationStatus.AVAILABLE,
        (
            EntryPathReasonCode.OUTCOME_RESOLVED
            if touched
            else EntryPathReasonCode.HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH
        ),
        float(max(Decimal("0"), high / reference_price - Decimal("1"))),
        float(min(Decimal("0"), low / reference_price - Decimal("1"))),
        float(close / reference_price - Decimal("1")),
    )


def _outcome_payload(
    *,
    decision_reference: ValidationArtifactReference,
    next_session_date: date,
    checkpoint_prices: tuple[tuple[str, Decimal], ...],
    path_session_ohlc: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...],
    target_protocol: OutcomeTargetProtocol | _ProtocolIdentity,
    retrieved_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": "free-historical-multi-horizon-outcome/v1",
        "decision_reference": decision_reference.to_canonical_dict(),
        "next_session_date": next_session_date.isoformat(),
        "checkpoint_prices": [[name, str(value)] for name, value in checkpoint_prices],
        "path_session_ohlc": [
            [session, str(open_price), str(high), str(low), str(close)]
            for session, open_price, high, low, close in path_session_ohlc
        ],
        "target_protocol_id": str(target_protocol.protocol_id),
        "target_protocol_hash": target_protocol.protocol_hash,
        "retrieved_at": timestamp(retrieved_at),
        "limitations": list(FREE_HISTORICAL_LIMITATIONS),
    }


__all__ = [
    "AShareBarProviderReader",
    "FREE_HISTORICAL_REGISTRY_VERSION",
    "FreeHistoricalBar",
    "FreeHistoricalBarReader",
    "FreeHistoricalDecision",
    "FreeHistoricalMultiHorizonOutcome",
    "FreeHistoricalSampleBuildResult",
    "FreeHistoricalSamplePipeline",
    "HistoricalSampleDatasetWriter",
]
