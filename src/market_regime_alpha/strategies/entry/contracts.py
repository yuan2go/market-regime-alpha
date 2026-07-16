"""Categorical path-dependent Entry research Target contracts.

These contracts describe future research labels. They do not authorize Entry proposals,
Portfolio decisions, orders, or execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from hashlib import sha256
import json
import math

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime


ENTRY_PATH_TARGET_SCHEMA_VERSION = "entry-path-target-v1"
NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1 = (
    "NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1"
)
DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1 = (
    "DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1"
)
DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1 = (
    "DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1"
)


def _require_text(label: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_optional_positive_price(label: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{label} must be positive and finite when present")


class EntryPathOutcome(str, Enum):
    """Mutually exclusive resolved Entry competing-event outcomes."""

    UP_FIRST = "UP_FIRST"
    DOWN_FIRST = "DOWN_FIRST"
    TIMEOUT = "TIMEOUT"


class EntryPathObservationStatus(str, Enum):
    """Availability and resolution state of one Entry path Target observation."""

    AVAILABLE = "AVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    INVALID = "INVALID"
    NOT_YET_OBSERVED = "NOT_YET_OBSERVED"


class EntryPathTriggerType(str, Enum):
    """Auditable daily-evidence event that terminated path evaluation."""

    OPEN_GAP_UP = "OPEN_GAP_UP"
    OPEN_GAP_DOWN = "OPEN_GAP_DOWN"
    INTRADAY_HIGH_ONLY = "INTRADAY_HIGH_ONLY"
    INTRADAY_LOW_ONLY = "INTRADAY_LOW_ONLY"
    INTRADAY_DUAL_TOUCH_UNORDERED = "INTRADAY_DUAL_TOUCH_UNORDERED"
    HORIZON_EXHAUSTED = "HORIZON_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class EntryBarrierSpec:
    """Complete versioned semantics of one Entry competing-event Target."""

    upper_return: float
    lower_return: float
    horizon_sessions: int
    price_adjustment_basis: str
    target_start_convention: str = NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
    reference_price_convention: str = (
        DECISION_TIME_1455_SNAPSHOT_REFERENCE_PRICE_V1
    )
    path_ordering_convention: str = (
        DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1
    )
    schema_version: str = ENTRY_PATH_TARGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for label, numeric_value in (
            ("upper_return", self.upper_return),
            ("lower_return", self.lower_return),
        ):
            if isinstance(numeric_value, bool) or not math.isfinite(
                float(numeric_value)
            ):
                raise ValueError(f"{label} must be finite and non-boolean")
        if self.upper_return <= 0.0:
            raise ValueError("upper_return must be positive")
        if self.lower_return >= 0.0:
            raise ValueError("lower_return must be negative")
        if isinstance(self.horizon_sessions, bool) or not isinstance(
            self.horizon_sessions,
            int,
        ):
            raise TypeError("horizon_sessions must be an integer")
        if self.horizon_sessions <= 0:
            raise ValueError("horizon_sessions must be positive")
        for label, text_value in (
            ("price_adjustment_basis", self.price_adjustment_basis),
            ("target_start_convention", self.target_start_convention),
            ("reference_price_convention", self.reference_price_convention),
            ("path_ordering_convention", self.path_ordering_convention),
            ("schema_version", self.schema_version),
        ):
            _require_text(label, text_value)


@dataclass(frozen=True, slots=True)
class EntryPathTargetContract:
    """Identified Entry path Target and the complete semantics it represents."""

    target_id: TargetId
    name: str
    spec: EntryBarrierSpec

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, TargetId):
            raise TypeError("target_id must be a TargetId")
        _require_text("name", self.name)
        if not isinstance(self.spec, EntryBarrierSpec):
            raise TypeError("spec must be an EntryBarrierSpec")
        if self.target_id != _target_id(self.spec):
            raise ValueError("target_id must represent the complete Entry barrier semantics")


@dataclass(frozen=True, slots=True)
class EntryPathObservation:
    """One categorical Entry Target observation with complete audit evidence."""

    symbol: str
    status: EntryPathObservationStatus
    outcome: EntryPathOutcome | None
    reference_price: float | None
    upper_price: float | None
    lower_price: float | None
    event_session_date: date | None
    event_session_index: int | None
    trigger_type: EntryPathTriggerType | None
    evaluated_session_dates: tuple[date, ...]
    first_missing_session_date: date | None
    reason_code: str
    observed_at: AvailabilityTime | None

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        if not isinstance(self.status, EntryPathObservationStatus):
            raise TypeError("status must be an EntryPathObservationStatus")
        if self.outcome is not None and not isinstance(self.outcome, EntryPathOutcome):
            raise TypeError("outcome must be an EntryPathOutcome or None")
        if self.trigger_type is not None and not isinstance(
            self.trigger_type,
            EntryPathTriggerType,
        ):
            raise TypeError("trigger_type must be an EntryPathTriggerType or None")
        for label, value in (
            ("reference_price", self.reference_price),
            ("upper_price", self.upper_price),
            ("lower_price", self.lower_price),
        ):
            _require_optional_positive_price(label, value)
        price_presence = tuple(
            value is not None
            for value in (self.reference_price, self.upper_price, self.lower_price)
        )
        if any(price_presence) and not all(price_presence):
            raise ValueError("reference and barrier prices must be present together")
        if all(price_presence):
            assert self.reference_price is not None
            assert self.upper_price is not None
            assert self.lower_price is not None
            if not self.lower_price < self.reference_price < self.upper_price:
                raise ValueError("barrier prices must satisfy lower < reference < upper")
        if (self.event_session_date is None) != (self.event_session_index is None):
            raise ValueError("event session date and index must be present together")
        if self.event_session_index is not None:
            if isinstance(self.event_session_index, bool) or not isinstance(
                self.event_session_index,
                int,
            ):
                raise TypeError("event_session_index must be an integer or None")
            if self.event_session_index <= 0:
                raise ValueError("event_session_index must be positive")
        if tuple(sorted(self.evaluated_session_dates)) != self.evaluated_session_dates:
            raise ValueError("evaluated_session_dates must be chronological")
        if len(self.evaluated_session_dates) != len(set(self.evaluated_session_dates)):
            raise ValueError("evaluated_session_dates must be unique")
        if self.event_session_date is not None:
            if not self.evaluated_session_dates:
                raise ValueError("event session requires evaluated session evidence")
            if self.event_session_date != self.evaluated_session_dates[-1]:
                raise ValueError("event session must be the last evaluated session")
            if self.event_session_index != len(self.evaluated_session_dates):
                raise ValueError("event session index must match evaluated session count")
        if self.first_missing_session_date in self.evaluated_session_dates:
            raise ValueError("first missing session cannot be evaluated")
        _require_text("reason_code", self.reason_code)
        if self.observed_at is not None and not isinstance(
            self.observed_at,
            AvailabilityTime,
        ):
            raise TypeError("observed_at must be an AvailabilityTime or None")
        self._validate_state()

    def _validate_state(self) -> None:
        if self.status is EntryPathObservationStatus.AVAILABLE:
            self._require_prices_event_and_observed()
            if self.outcome is None:
                raise ValueError("AVAILABLE Entry path observation requires outcome")
            if self.first_missing_session_date is not None:
                raise ValueError("AVAILABLE observation cannot carry a missing session")
            expected_triggers = {
                EntryPathOutcome.UP_FIRST: {
                    EntryPathTriggerType.OPEN_GAP_UP,
                    EntryPathTriggerType.INTRADAY_HIGH_ONLY,
                },
                EntryPathOutcome.DOWN_FIRST: {
                    EntryPathTriggerType.OPEN_GAP_DOWN,
                    EntryPathTriggerType.INTRADAY_LOW_ONLY,
                },
                EntryPathOutcome.TIMEOUT: {
                    EntryPathTriggerType.HORIZON_EXHAUSTED,
                },
            }
            if self.trigger_type not in expected_triggers[self.outcome]:
                raise ValueError("AVAILABLE outcome and trigger_type are inconsistent")
            return
        if self.outcome is not None:
            raise ValueError("non-AVAILABLE Entry path observation must not carry outcome")
        if self.status is EntryPathObservationStatus.AMBIGUOUS:
            self._require_prices_event_and_observed()
            if (
                self.trigger_type
                is not EntryPathTriggerType.INTRADAY_DUAL_TOUCH_UNORDERED
            ):
                raise ValueError("AMBIGUOUS observation requires dual-touch trigger")
            if self.first_missing_session_date is not None:
                raise ValueError("AMBIGUOUS observation cannot carry a missing session")
            return
        if self.status is EntryPathObservationStatus.MISSING:
            self._require_prices_and_observed()
            if self.event_session_date is not None or self.trigger_type is not None:
                raise ValueError("MISSING observation cannot carry an event")
            if self.first_missing_session_date is None:
                raise ValueError("MISSING observation requires first missing session")
            return
        if self.status is EntryPathObservationStatus.INVALID:
            if self.event_session_date is not None or self.trigger_type is not None:
                raise ValueError("INVALID observation cannot carry an event")
            if self.first_missing_session_date is not None:
                raise ValueError("INVALID observation cannot carry a missing session")
            if self.evaluated_session_dates:
                raise ValueError("INVALID observation cannot carry evaluated sessions")
            if self.observed_at is None:
                raise ValueError("INVALID observation requires observed_at")
            return
        self._require_prices()
        if self.event_session_date is not None or self.trigger_type is not None:
            raise ValueError("NOT_YET_OBSERVED observation cannot carry an event")
        if self.first_missing_session_date is not None:
            raise ValueError("NOT_YET_OBSERVED cannot carry a missing session")
        if self.observed_at is not None:
            raise ValueError("NOT_YET_OBSERVED must not carry observed_at")

    def _require_prices(self) -> None:
        if any(
            value is None
            for value in (self.reference_price, self.upper_price, self.lower_price)
        ):
            raise ValueError("observation state requires reference and barrier prices")

    def _require_prices_and_observed(self) -> None:
        self._require_prices()
        if self.observed_at is None:
            raise ValueError("observation state requires observed_at")

    def _require_prices_event_and_observed(self) -> None:
        self._require_prices_and_observed()
        if self.event_session_date is None or self.trigger_type is None:
            raise ValueError("observation state requires event session and trigger")


@dataclass(frozen=True, slots=True)
class EntryPathTargetMaterialization:
    """Identified collection of Entry path Target observations for one Decision Time."""

    artifact_id: ArtifactId
    target_id: TargetId
    source_dataset_ids: tuple[DatasetId, ...]
    calendar_artifact_id: ArtifactId
    universe_id: UniverseId
    decision_time: DecisionTime
    materialized_at: AsOfTime
    code_revision: str
    config_hash: str
    observations: tuple[EntryPathObservation, ...]

    def __post_init__(self) -> None:
        if not self.source_dataset_ids:
            raise ValueError("Entry path materialization requires source Dataset identities")
        if len(self.source_dataset_ids) != len(set(self.source_dataset_ids)):
            raise ValueError("source_dataset_ids must be unique")
        if tuple(sorted(self.source_dataset_ids, key=str)) != self.source_dataset_ids:
            raise ValueError("source_dataset_ids must be sorted")
        if self.materialized_at.value <= self.decision_time.value:
            raise ValueError("Entry path materialization must occur after Decision Time")
        _require_text("code_revision", self.code_revision)
        _require_text("config_hash", self.config_hash)
        symbols = tuple(item.symbol for item in self.observations)
        if len(symbols) != len(set(symbols)):
            raise ValueError("Entry path observations must have unique symbols")
        if tuple(sorted(symbols)) != symbols:
            raise ValueError("Entry path observations must be sorted by symbol")
        for observation in self.observations:
            if (
                observation.observed_at is not None
                and observation.observed_at.value > self.materialized_at.value
            ):
                raise ValueError("Target observed_at cannot follow materialized_at")


def build_entry_path_target_contract(
    spec: EntryBarrierSpec,
) -> EntryPathTargetContract:
    """Build the deterministic Target identity for complete Entry path semantics."""

    if not isinstance(spec, EntryBarrierSpec):
        raise TypeError("spec must be an EntryBarrierSpec")
    return EntryPathTargetContract(
        target_id=_target_id(spec),
        name="Entry Competing-Event Path Target",
        spec=spec,
    )


def _target_id(spec: EntryBarrierSpec) -> TargetId:
    payload = {
        "schema_version": spec.schema_version,
        "upper_return": spec.upper_return,
        "lower_return": spec.lower_return,
        "horizon_sessions": spec.horizon_sessions,
        "target_start_convention": spec.target_start_convention,
        "reference_price_convention": spec.reference_price_convention,
        "path_ordering_convention": spec.path_ordering_convention,
        "price_adjustment_basis": spec.price_adjustment_basis,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return TargetId(f"target-entry-path-{digest[:24]}")
