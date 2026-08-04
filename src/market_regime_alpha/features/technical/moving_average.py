"""Deterministic Decimal simple-moving-average observable.

The calculation is deliberately independent of repositories, execution code,
and wall-clock time.  It describes a technical feature only; it does not
express a Signal, Decision, or trading action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, Mapping, cast

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.features.artifact import bind_feature_artifact_identity
from market_regime_alpha.features.model_contracts import (
    FeatureArtifact,
    FeatureComputationRequest,
)


MOVING_AVERAGE_CONFIGURATION_SCHEMA = "moving-average-configuration-v1"
MOVING_AVERAGE_OBSERVATION_SCHEMA = "moving-average-observation-v1"
SIMPLE_MOVING_AVERAGE_FEATURE_ID = FeatureDefinitionId(
    "technical.simple-moving-average"
)
SIMPLE_MOVING_AVERAGE_MODEL_ID = ModelId("technical.simple-moving-average")


def _require_canonical_time(label: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.microsecond != 0:
        raise ValueError(f"{label} must have whole-second precision")


def _require_positive_decimal(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{label} must be finite")
    if value <= Decimal("0"):
        raise ValueError(f"{label} must be positive")


def _require_positive_integer(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")


@dataclass(frozen=True, slots=True)
class NormalizedCloseBar:
    """One normalized close with explicit event and availability time."""

    symbol: str
    market_date: date
    close: Decimal
    available_at: datetime

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not isinstance(self.market_date, date) or isinstance(
            self.market_date, datetime
        ):
            raise TypeError("market_date must be a date")
        _require_positive_decimal("close", self.close)
        _require_canonical_time("available_at", self.available_at)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "market_date": self.market_date.isoformat(),
            "close": str(self.close),
            "available_at": canonical_datetime(self.available_at),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, object]
    ) -> NormalizedCloseBar:
        if set(payload) != {"symbol", "market_date", "close", "available_at"}:
            raise ValueError("NormalizedCloseBar fields mismatch")
        return cls(
            symbol=_text(payload["symbol"], "symbol"),
            market_date=_date(payload["market_date"], "market_date"),
            close=_decimal(payload["close"], "close"),
            available_at=_datetime(payload["available_at"], "available_at"),
        )


@dataclass(frozen=True, slots=True)
class MovingAverageConfiguration:
    """Immutable, content-addressed choices for one simple moving average."""

    configuration_id: ArtifactId
    configuration_version: str
    window: int
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_id, ArtifactId):
            raise TypeError("configuration_id must be an ArtifactId")
        require_text("configuration_version", self.configuration_version)
        _require_positive_integer("window", self.window)
        require_sha256("content_hash", self.content_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash:
            raise ValueError("Moving Average configuration hash mismatch")
        expected_id = f"moving-average-config-{expected_hash.split(':', 1)[1][:24]}"
        if str(self.configuration_id) != expected_id:
            raise ValueError("Moving Average configuration identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        configuration_version: str,
        window: int,
    ) -> MovingAverageConfiguration:
        require_text("configuration_version", configuration_version)
        _require_positive_integer("window", window)
        payload = {
            "schema_version": MOVING_AVERAGE_CONFIGURATION_SCHEMA,
            "configuration_version": configuration_version,
            "window": window,
        }
        content_hash = canonical_hash(payload)
        return cls(
            configuration_id=ArtifactId(
                f"moving-average-config-{content_hash.split(':', 1)[1][:24]}"
            ),
            configuration_version=configuration_version,
            window=window,
            content_hash=content_hash,
        )

    def semantic_payload(self) -> dict[str, str | int]:
        return {
            "schema_version": MOVING_AVERAGE_CONFIGURATION_SCHEMA,
            "configuration_version": self.configuration_version,
            "window": self.window,
        }

    def to_canonical_dict(self) -> dict[str, str | int]:
        return {
            "configuration_id": str(self.configuration_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, object]
    ) -> MovingAverageConfiguration:
        expected = {
            "configuration_id",
            "content_hash",
            "schema_version",
            "configuration_version",
            "window",
        }
        if set(payload) != expected:
            raise ValueError("MovingAverageConfiguration fields mismatch")
        if _text(payload["schema_version"], "schema_version") != (
            MOVING_AVERAGE_CONFIGURATION_SCHEMA
        ):
            raise ValueError("unsupported Moving Average configuration schema")
        window = payload["window"]
        if isinstance(window, bool) or not isinstance(window, int):
            raise ValueError("window must be an integer")
        return cls(
            configuration_id=ArtifactId(
                _text(payload["configuration_id"], "configuration_id")
            ),
            configuration_version=_text(
                payload["configuration_version"], "configuration_version"
            ),
            window=window,
            content_hash=_text(payload["content_hash"], "content_hash"),
        )


@dataclass(frozen=True, slots=True)
class MovingAverageObservation:
    """One replayable output row, including its exact normalized source close."""

    symbol: str
    market_date: date
    close: Decimal
    source_available_at: datetime
    available_at: datetime
    window: int
    observations_seen: int
    value: Decimal | None
    missing_reason: str | None
    schema_version: str = MOVING_AVERAGE_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != MOVING_AVERAGE_OBSERVATION_SCHEMA:
            raise ValueError("unsupported Moving Average observation schema")
        require_text("symbol", self.symbol)
        if not isinstance(self.market_date, date) or isinstance(
            self.market_date, datetime
        ):
            raise TypeError("market_date must be a date")
        _require_positive_decimal("close", self.close)
        _require_canonical_time("source_available_at", self.source_available_at)
        _require_canonical_time("available_at", self.available_at)
        if self.available_at < self.source_available_at:
            raise ValueError("feature available_at cannot precede source availability")
        _require_positive_integer("window", self.window)
        _require_positive_integer("observations_seen", self.observations_seen)
        if self.value is not None:
            _require_positive_decimal("value", self.value)
        if self.missing_reason is not None:
            require_text("missing_reason", self.missing_reason)
        if (self.value is None) == (self.missing_reason is None):
            raise ValueError("observation requires exactly one value or missing_reason")
        input_unavailable = bool(
            self.missing_reason
            and self.missing_reason.startswith("INPUT_DATA_")
        )
        if input_unavailable:
            if self.value is not None:
                raise ValueError("unavailable observations cannot contain a value")
        elif self.observations_seen < self.window:
            if self.value is not None or self.missing_reason != "WINDOW_NOT_READY":
                raise ValueError("warm-up observations require WINDOW_NOT_READY")
        elif self.missing_reason == "WINDOW_NOT_READY":
            raise ValueError("ready observations cannot use WINDOW_NOT_READY")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "market_date": self.market_date.isoformat(),
            "close": str(self.close),
            "source_available_at": canonical_datetime(self.source_available_at),
            "available_at": canonical_datetime(self.available_at),
            "window": self.window,
            "observations_seen": self.observations_seen,
            "value": str(self.value) if self.value is not None else None,
            "missing_reason": self.missing_reason,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, object]
    ) -> MovingAverageObservation:
        expected = {
            "schema_version",
            "symbol",
            "market_date",
            "close",
            "source_available_at",
            "available_at",
            "window",
            "observations_seen",
            "value",
            "missing_reason",
        }
        if set(payload) != expected:
            raise ValueError("MovingAverageObservation fields mismatch")
        window = _integer(payload["window"], "window")
        observations_seen = _integer(
            payload["observations_seen"], "observations_seen"
        )
        value = payload["value"]
        missing_reason = payload["missing_reason"]
        return cls(
            schema_version=_text(payload["schema_version"], "schema_version"),
            symbol=_text(payload["symbol"], "symbol"),
            market_date=_date(payload["market_date"], "market_date"),
            close=_decimal(payload["close"], "close"),
            source_available_at=_datetime(
                payload["source_available_at"], "source_available_at"
            ),
            available_at=_datetime(payload["available_at"], "available_at"),
            window=window,
            observations_seen=observations_seen,
            value=_decimal(value, "value") if value is not None else None,
            missing_reason=(
                _text(missing_reason, "missing_reason")
                if missing_reason is not None
                else None
            ),
        )


class SimpleMovingAverageComputer:
    """Pure implementation of a trailing arithmetic mean over close values."""

    feature_id = SIMPLE_MOVING_AVERAGE_FEATURE_ID
    model_id = SIMPLE_MOVING_AVERAGE_MODEL_ID
    model_version = "1.0.0"

    def compute(self, request: FeatureComputationRequest) -> FeatureArtifact:
        if not isinstance(request, FeatureComputationRequest):
            raise TypeError("request must be a FeatureComputationRequest")
        _require_canonical_time("as_of_time", request.as_of_time)
        _require_canonical_time("created_at", request.created_at)
        configuration = request.configuration
        if not isinstance(configuration, MovingAverageConfiguration):
            raise TypeError("configuration must be MovingAverageConfiguration")
        if (
            request.configuration_id != configuration.configuration_id
            or request.configuration_version != configuration.configuration_version
            or request.configuration_hash != configuration.content_hash
        ):
            raise ValueError("Moving Average configuration identity mismatch")

        bars = self._validated_bars(request)
        observations = self._compute_observations(
            bars=bars,
            configuration=configuration,
            availability=request.data_availability,
        )
        reason_codes: tuple[str, ...]
        if request.data_availability is not InputAvailabilityStatus.AVAILABLE:
            state = "DATA_UNAVAILABLE"
            score = None
            reason_codes = (f"INPUT_DATA_{request.data_availability.value}",)
        elif not observations:
            state = "DATA_INSUFFICIENT"
            score = None
            reason_codes = ("NO_OBSERVATIONS",)
        else:
            final = observations[-1]
            score = final.value
            if score is None:
                state = "DATA_INSUFFICIENT"
                reason_codes = ("WINDOW_NOT_READY",)
            else:
                state = "AVAILABLE"
                reason_codes = (
                    ("FEATURE_COMPUTED", "WINDOW_NOT_READY")
                    if any(item.value is None for item in observations)
                    else ("FEATURE_COMPUTED",)
                )

        unbound = FeatureArtifact(
            artifact_id=ArtifactId("feature-artifact-unbound"),
            content_hash="sha256:" + "0" * 64,
            feature_id=self.feature_id,
            dataset_id=request.dataset_id,
            model_id=self.model_id,
            model_version=self.model_version,
            configuration_id=configuration.configuration_id,
            configuration_version=configuration.configuration_version,
            configuration_hash=configuration.content_hash,
            input_artifact_ids=request.input_artifact_ids,
            input_hashes=request.input_hashes,
            as_of_time=request.as_of_time,
            created_at=request.created_at,
            data_availability=request.data_availability,
            state=state,
            score=score,
            reason_codes=reason_codes,
            limitations=("NO_TRADING_AUTHORITY", "RESEARCH_ONLY"),
            validation_status="UNVALIDATED",
            observations=observations,
            configuration_parameters=(("window", str(configuration.window)),),
        )
        return bind_feature_artifact_identity(unbound)

    @staticmethod
    def _validated_bars(
        request: FeatureComputationRequest,
    ) -> tuple[NormalizedCloseBar, ...]:
        if any(
            not isinstance(item, NormalizedCloseBar)
            for item in request.normalized_data
        ):
            raise TypeError("normalized_data must contain NormalizedCloseBar values")
        bars = cast(tuple[NormalizedCloseBar, ...], request.normalized_data)
        symbols = {item.symbol for item in bars}
        if len(symbols) > 1:
            raise ValueError("Moving Average input must contain one symbol")
        dates = tuple(item.market_date for item in bars)
        if len(dates) != len(set(dates)):
            raise ValueError("Moving Average input contains duplicate market dates")
        if dates != tuple(sorted(dates)):
            raise ValueError("Moving Average bars must be strictly sorted")
        if any(item.available_at > request.as_of_time for item in bars):
            raise ValueError("Moving Average bar is available after as_of_time")
        if any(item.market_date > request.as_of_time.date() for item in bars):
            raise ValueError("Moving Average market_date is after as_of_time")
        return bars

    @staticmethod
    def _compute_observations(
        *,
        bars: tuple[NormalizedCloseBar, ...],
        configuration: MovingAverageConfiguration,
        availability: InputAvailabilityStatus,
    ) -> tuple[MovingAverageObservation, ...]:
        observations: list[MovingAverageObservation] = []
        for index, bar in enumerate(bars):
            observations_seen = index + 1
            relevant = bars[max(0, observations_seen - configuration.window) : observations_seen]
            available_at = max(item.available_at for item in relevant)
            if availability is not InputAvailabilityStatus.AVAILABLE:
                value = None
                missing_reason = f"INPUT_DATA_{availability.value}"
            elif observations_seen < configuration.window:
                value = None
                missing_reason = "WINDOW_NOT_READY"
            else:
                with localcontext(Context(prec=34, rounding=ROUND_HALF_EVEN)):
                    window_sum = sum(
                        (item.close for item in relevant), start=Decimal("0")
                    )
                    value = window_sum / Decimal(configuration.window)
                missing_reason = None
            observations.append(
                MovingAverageObservation(
                    symbol=bar.symbol,
                    market_date=bar.market_date,
                    close=bar.close,
                    source_available_at=bar.available_at,
                    available_at=available_at,
                    window=configuration.window,
                    observations_seen=observations_seen,
                    value=value,
                    missing_reason=missing_reason,
                )
            )
        return tuple(observations)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _decimal(value: object, label: str) -> Decimal:
    text = _text(value, label)
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a Decimal string") from exc


def _date(value: object, label: str) -> date:
    text = _text(value, label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _datetime(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO datetime") from exc


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


__all__ = [
    "MOVING_AVERAGE_CONFIGURATION_SCHEMA",
    "MOVING_AVERAGE_OBSERVATION_SCHEMA",
    "SIMPLE_MOVING_AVERAGE_FEATURE_ID",
    "MovingAverageConfiguration",
    "MovingAverageObservation",
    "NormalizedCloseBar",
    "SimpleMovingAverageComputer",
]
