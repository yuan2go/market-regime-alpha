"""Research-only multi-horizon PathForecast over versioned Entry targets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import fmean
from typing import Any, Mapping, cast
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId, ModelId, TargetId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.forecasting.contracts import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
    ReturnQuantile,
)
from market_regime_alpha.signals.contracts import SignalSnapshot
from market_regime_alpha.signals.decimal_model import CanonicalSignalSnapshotV3
from market_regime_alpha.strategies.entry.contracts import (
    EntryBarrierSpec,
    EntryPathObservationStatus,
    EntryPathReasonCode,
    EntryPathTargetContract,
    build_entry_path_target_contract,
)


PATH_FORECAST_CONFIG_SCHEMA = "path-forecast-config-v1"
PATH_FORECAST_SAMPLE_SCHEMA = "path-forecast-sample-v1"
SignalSnapshotAuthority = SignalSnapshot | CanonicalSignalSnapshotV3


def _require_text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class PathForecastConfig:
    """Explicit exploratory aggregation and identified Entry target semantics."""

    profile_id: str
    model_id: ModelId
    model_version: str
    decision_profile_id: str
    decision_time_local: str
    timezone_name: str
    market_scope: str
    allowed_side: str
    target_contract: EntryPathTargetContract
    horizon_label: str
    return_quantile_levels: tuple[float, ...]
    minimum_usable_samples: int
    aggregation_method: str
    schema_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("profile_id", self.profile_id),
            ("model_version", self.model_version),
            ("decision_profile_id", self.decision_profile_id),
            ("decision_time_local", self.decision_time_local),
            ("timezone_name", self.timezone_name),
            ("market_scope", self.market_scope),
            ("allowed_side", self.allowed_side),
            ("horizon_label", self.horizon_label),
            ("aggregation_method", self.aggregation_method),
            ("schema_version", self.schema_version),
        ):
            _require_text(label, value)
        if self.schema_version != PATH_FORECAST_CONFIG_SCHEMA:
            raise ValueError("unsupported PathForecast configuration schema")
        if self.market_scope != "A_SHARE" or self.allowed_side != "LONG_ONLY":
            raise ValueError("PathForecast V1 is restricted to A_SHARE LONG_ONLY")
        try:
            datetime.strptime(self.decision_time_local, "%H:%M")
            ZoneInfo(self.timezone_name)
        except (ValueError, KeyError) as exc:
            raise ValueError("invalid versioned PathForecast decision profile") from exc
        if not isinstance(self.target_contract, EntryPathTargetContract):
            raise TypeError("target_contract must be an EntryPathTargetContract")
        if (
            not self.return_quantile_levels
            or self.return_quantile_levels
            != tuple(sorted(set(self.return_quantile_levels)))
            or any(not 0.0 < item < 1.0 for item in self.return_quantile_levels)
        ):
            raise ValueError("return quantile levels must be sorted, unique and within (0, 1)")
        if self.minimum_usable_samples <= 0:
            raise ValueError("minimum_usable_samples must be positive")
        if self.aggregation_method != "EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1":
            raise ValueError("unsupported PathForecast aggregation method")

    @property
    def configuration_hash(self) -> str:
        return canonical_hash(self.to_canonical_dict())

    @property
    def configuration_id(self) -> ArtifactId:
        digest = self.configuration_hash.split(":", 1)[1]
        return ArtifactId(f"path-forecast-config-{digest[:24]}")

    def to_canonical_dict(self) -> dict[str, Any]:
        spec = self.target_contract.spec
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "decision_profile_id": self.decision_profile_id,
            "decision_time_local": self.decision_time_local,
            "timezone_name": self.timezone_name,
            "market_scope": self.market_scope,
            "allowed_side": self.allowed_side,
            "target_contract": {
                "target_id": str(self.target_contract.target_id),
                "name": self.target_contract.name,
                "spec": {
                    "upper_return": spec.upper_return,
                    "lower_return": spec.lower_return,
                    "horizon_sessions": spec.horizon_sessions,
                    "price_adjustment_basis": spec.price_adjustment_basis,
                    "target_start_convention": spec.target_start_convention,
                    "reference_price_convention": spec.reference_price_convention,
                    "path_ordering_convention": spec.path_ordering_convention,
                    "schema_version": spec.schema_version,
                },
            },
            "horizon_label": self.horizon_label,
            "return_quantile_levels": list(self.return_quantile_levels),
            "minimum_usable_samples": self.minimum_usable_samples,
            "aggregation_method": self.aggregation_method,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PathForecastConfig:
        expected = {
            "schema_version",
            "profile_id",
            "model_id",
            "model_version",
            "decision_profile_id",
            "decision_time_local",
            "timezone_name",
            "market_scope",
            "allowed_side",
            "target_contract",
            "horizon_label",
            "return_quantile_levels",
            "minimum_usable_samples",
            "aggregation_method",
        }
        target = payload.get("target_contract")
        levels = payload.get("return_quantile_levels")
        if set(payload) != expected or not isinstance(target, dict) or not isinstance(levels, list):
            raise ValueError("PathForecastConfig fields mismatch")
        if set(target) != {"target_id", "name", "spec"} or not isinstance(target["spec"], dict):
            raise ValueError("PathForecast target contract fields mismatch")
        spec_payload = target["spec"]
        if set(spec_payload) != {
            "upper_return",
            "lower_return",
            "horizon_sessions",
            "price_adjustment_basis",
            "target_start_convention",
            "reference_price_convention",
            "path_ordering_convention",
            "schema_version",
        }:
            raise ValueError("PathForecast Entry target spec fields mismatch")
        contract = build_entry_path_target_contract(
            EntryBarrierSpec(
                upper_return=float(spec_payload["upper_return"]),
                lower_return=float(spec_payload["lower_return"]),
                horizon_sessions=int(spec_payload["horizon_sessions"]),
                price_adjustment_basis=str(spec_payload["price_adjustment_basis"]),
                target_start_convention=str(spec_payload["target_start_convention"]),
                reference_price_convention=str(spec_payload["reference_price_convention"]),
                path_ordering_convention=str(spec_payload["path_ordering_convention"]),
                schema_version=str(spec_payload["schema_version"]),
            )
        )
        if str(contract.target_id) != str(target["target_id"]) or contract.name != str(target["name"]):
            raise ValueError("PathForecast target contract is not reconstructible")
        return cls(
            profile_id=str(payload["profile_id"]),
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            decision_profile_id=str(payload["decision_profile_id"]),
            decision_time_local=str(payload["decision_time_local"]),
            timezone_name=str(payload["timezone_name"]),
            market_scope=str(payload["market_scope"]),
            allowed_side=str(payload["allowed_side"]),
            target_contract=contract,
            horizon_label=str(payload["horizon_label"]),
            return_quantile_levels=tuple(float(item) for item in levels),
            minimum_usable_samples=int(payload["minimum_usable_samples"]),
            aggregation_method=str(payload["aggregation_method"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PathForecastSample:
    sample_id: ArtifactId
    source_artifact_id: ArtifactId
    source_content_hash: str
    symbol: str
    target_id: TargetId
    sample_decision_time: DecisionTime
    available_at: AvailabilityTime
    observation_status: EntryPathObservationStatus
    observation_reason_code: EntryPathReasonCode
    realized_mfe: float | None
    realized_mae: float | None
    realized_return: float | None
    schema_version: str

    def __post_init__(self) -> None:
        _require_text("symbol", self.symbol)
        require_sha256("source_content_hash", self.source_content_hash)
        if self.schema_version != PATH_FORECAST_SAMPLE_SCHEMA:
            raise ValueError("unsupported PathForecast sample schema")
        if self.available_at.value <= self.sample_decision_time.value:
            raise ValueError("Path sample availability must follow its DecisionTime")
        values = (self.realized_mfe, self.realized_mae, self.realized_return)
        if self.observation_status is EntryPathObservationStatus.AVAILABLE:
            if any(value is None for value in values):
                raise ValueError("AVAILABLE Path sample requires MFE, MAE and return")
            assert self.realized_mfe is not None and self.realized_mae is not None
            if self.realized_mfe < 0.0 or self.realized_mae > 0.0:
                raise ValueError("Path sample requires MFE >= 0 and MAE <= 0")
        elif any(value is not None for value in values):
            raise ValueError("unresolved Path sample cannot carry realized estimates")
        for value in values:
            if value is not None and not isfinite(value):
                raise ValueError("Path sample estimates must be finite")
        if (
            self.observation_status is EntryPathObservationStatus.AMBIGUOUS
            and self.observation_reason_code
            is not EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
        ):
            raise ValueError("AMBIGUOUS Path sample requires dual-touch reason")
        if (
            self.observation_status is EntryPathObservationStatus.MISSING
            and self.observation_reason_code is not EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING
        ):
            raise ValueError("MISSING Path sample requires missing future bar reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sample_id": str(self.sample_id),
            "source_artifact_id": str(self.source_artifact_id),
            "source_content_hash": self.source_content_hash,
            "symbol": self.symbol,
            "target_id": str(self.target_id),
            "sample_decision_time": self.sample_decision_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "observation_status": self.observation_status.value,
            "observation_reason_code": self.observation_reason_code.value,
            "realized_mfe": self.realized_mfe,
            "realized_mae": self.realized_mae,
            "realized_return": self.realized_return,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PathForecastSample:
        expected = {
            "schema_version",
            "sample_id",
            "source_artifact_id",
            "source_content_hash",
            "symbol",
            "target_id",
            "sample_decision_time",
            "available_at",
            "observation_status",
            "observation_reason_code",
            "realized_mfe",
            "realized_mae",
            "realized_return",
        }
        if set(payload) != expected:
            raise ValueError("PathForecastSample fields mismatch")
        return cls(
            sample_id=ArtifactId(str(payload["sample_id"])),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_content_hash=str(payload["source_content_hash"]),
            symbol=str(payload["symbol"]),
            target_id=TargetId(str(payload["target_id"])),
            sample_decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["sample_decision_time"]))
            ),
            available_at=AvailabilityTime(
                datetime.fromisoformat(str(payload["available_at"]))
            ),
            observation_status=EntryPathObservationStatus(
                str(payload["observation_status"])
            ),
            observation_reason_code=EntryPathReasonCode(
                str(payload["observation_reason_code"])
            ),
            realized_mfe=_optional_float(payload["realized_mfe"]),
            realized_mae=_optional_float(payload["realized_mae"]),
            realized_return=_optional_float(payload["realized_return"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PathForecastArtifact:
    forecast: PathForecast
    signal_snapshot: SignalSnapshotAuthority
    configuration: PathForecastConfig
    samples: tuple[PathForecastSample, ...]

    def __post_init__(self) -> None:
        if self.forecast.envelope.configuration_id != self.configuration.configuration_id:
            raise ValueError("PathForecast configuration identity mismatch")
        if self.forecast.symbol != self.signal_snapshot.symbol:
            raise ValueError("PathForecast and Signal symbol mismatch")

    @property
    def artifact_id(self) -> ArtifactId:
        return self.forecast.envelope.artifact_id

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "forecast": self.forecast.to_canonical_dict(),
            "signal_snapshot": self.signal_snapshot.to_canonical_dict(),
            "configuration": self.configuration.to_canonical_dict(),
            "samples": [item.to_canonical_dict() for item in self.samples],
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PathForecastArtifact:
        expected = {"forecast", "signal_snapshot", "configuration", "samples"}
        forecast = payload.get("forecast")
        signal = payload.get("signal_snapshot")
        config = payload.get("configuration")
        samples = payload.get("samples")
        if (
            set(payload) != expected
            or not isinstance(forecast, dict)
            or not isinstance(signal, dict)
            or not isinstance(config, dict)
            or not isinstance(samples, list)
        ):
            raise ValueError("PathForecastArtifact fields mismatch")
        signal_schema = signal.get("schema_version")
        restored_signal: SignalSnapshotAuthority = (
            CanonicalSignalSnapshotV3.from_canonical_dict(signal)
            if signal_schema == "canonical-signal-snapshot-v3"
            else SignalSnapshot.from_canonical_dict(signal)
        )
        return cls(
            forecast=PathForecast.from_canonical_dict(forecast),
            signal_snapshot=restored_signal,
            configuration=PathForecastConfig.from_canonical_dict(config),
            samples=tuple(PathForecastSample.from_canonical_dict(_object(item)) for item in samples),
        )


def build_path_forecast(
    *,
    signal_snapshot: SignalSnapshotAuthority,
    configuration: PathForecastConfig,
    samples: tuple[PathForecastSample, ...],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> PathForecastArtifact:
    """Aggregate only resolved historical samples available by DecisionTime."""

    return _build_path_forecast(
        signal_snapshot=signal_snapshot,
        configuration=configuration,
        samples=samples,
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        retrospective_event_ends=None,
    )


def build_retrospective_path_forecast(
    *,
    signal_snapshot: SignalSnapshotAuthority,
    configuration: PathForecastConfig,
    samples: tuple[PathForecastSample, ...],
    sample_event_ends: Mapping[ArtifactId, datetime],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
) -> PathForecastArtifact:
    """Replay the canonical aggregation using explicit historical event times.

    Free archives retain their true later retrieval timestamps, so they cannot
    pass the live AvailabilityTime gate.  This adapter requires an exact event
    end for every sample and rejects any outcome not complete by DecisionTime.
    It never upgrades the resulting forecast beyond exploratory PIT-incomplete
    evidence.
    """

    if set(sample_event_ends) != {item.sample_id for item in samples}:
        raise ValueError("Retrospective PathForecast event-end scope mismatch")
    for sample in samples:
        event_end = sample_event_ends[sample.sample_id]
        if event_end.tzinfo is None or event_end.utcoffset() is None:
            raise ValueError("Retrospective PathForecast event end must be aware")
        if event_end <= sample.sample_decision_time.value:
            raise ValueError("Retrospective PathForecast outcome did not follow DecisionTime")
        if event_end > decision_time.value:
            raise ValueError("Retrospective PathForecast sample leaks a future outcome")
    return _build_path_forecast(
        signal_snapshot=signal_snapshot,
        configuration=configuration,
        samples=samples,
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        retrospective_event_ends=sample_event_ends,
    )


def _build_path_forecast(
    *,
    signal_snapshot: SignalSnapshotAuthority,
    configuration: PathForecastConfig,
    samples: tuple[PathForecastSample, ...],
    decision_time: DecisionTime,
    created_at: datetime,
    code_revision: str,
    retrospective_event_ends: Mapping[ArtifactId, datetime] | None,
) -> PathForecastArtifact:

    local = decision_time.value.astimezone(ZoneInfo(configuration.timezone_name))
    if local.strftime("%H:%M") != configuration.decision_time_local:
        raise ValueError("DecisionTime does not match versioned PathForecast profile")
    if signal_snapshot.envelope.decision_time != decision_time:
        raise ValueError("PathForecast DecisionTime must match SignalSnapshot")
    if len({item.sample_id for item in samples}) != len(samples):
        raise ValueError("PathForecast sample identities must be unique")
    for sample in samples:
        if sample.target_id != configuration.target_contract.target_id:
            raise ValueError("PathForecast sample TargetId mismatch")
        if sample.symbol != signal_snapshot.symbol:
            raise ValueError("PathForecast V1 samples must match forecast symbol")
        if sample.sample_decision_time.value >= decision_time.value:
            raise ValueError("PathForecast sample DecisionTime is not historical")
        if (
            retrospective_event_ends is None
            and sample.available_at.value > decision_time.value
        ):
            raise ValueError("PathForecast sample AvailabilityTime exceeds DecisionTime")
    usable = tuple(
        item
        for item in samples
        if item.observation_status is EntryPathObservationStatus.AVAILABLE
    )
    excluded = tuple(item for item in samples if item not in usable)
    if len(usable) < configuration.minimum_usable_samples:
        status = PathForecastStatus.DATA_INSUFFICIENT
        calibration = CalibrationStatus.DATA_INSUFFICIENT
        expected_mfe = None
        expected_mae = None
        quantiles: tuple[ReturnQuantile, ...] = ()
        reasons = tuple(
            sorted(
                {
                    "MINIMUM_PATH_SAMPLE_COUNT_NOT_MET",
                    *(item.observation_reason_code.value for item in excluded),
                }
            )
        )
    else:
        status = PathForecastStatus.AVAILABLE_FOR_RESEARCH
        calibration = CalibrationStatus.NOT_CALIBRATED
        mfes = [item.realized_mfe for item in usable]
        maes = [item.realized_mae for item in usable]
        returns = [item.realized_return for item in usable]
        assert all(item is not None for item in mfes)
        assert all(item is not None for item in maes)
        assert all(item is not None for item in returns)
        mfe_values = [cast(float, item) for item in mfes]
        mae_values = [cast(float, item) for item in maes]
        return_values = sorted(cast(float, item) for item in returns)
        expected_mfe = fmean(mfe_values)
        expected_mae = fmean(mae_values)
        quantiles = tuple(
            ReturnQuantile(level, _linear_quantile(return_values, level))
            for level in configuration.return_quantile_levels
        )
        reasons = tuple(
            sorted(
                {
                    "PATH_FORECAST_UNCALIBRATED_RESEARCH_ONLY",
                    *(item.observation_reason_code.value for item in excluded),
                }
            )
        )
    if retrospective_event_ends is not None:
        reasons = tuple(
            sorted(
                {
                    *reasons,
                    "FORMAL_OOS_FALSE",
                    "PIT_INCOMPLETE",
                    "RETROSPECTIVE_EVENT_TIME",
                }
            )
        )
    spec = configuration.target_contract.spec
    payload = {
        "symbol": signal_snapshot.symbol,
        "target_id": str(configuration.target_contract.target_id),
        "forecast_horizon": configuration.horizon_label,
        "upper_barrier_return": spec.upper_return,
        "lower_barrier_return": spec.lower_return,
        "expected_mfe": expected_mfe,
        "expected_mae": expected_mae,
        "return_quantiles": [
            {"probability": item.probability, "return_value": item.return_value}
            for item in quantiles
        ],
        "calibration_status": calibration.value,
        "forecast_status": status.value,
        "usable_sample_count": len(usable),
        "excluded_sample_count": len(excluded),
        "reason_codes": list(reasons),
    }
    input_pairs = {signal_snapshot.envelope.artifact_id: signal_snapshot.envelope.content_hash}
    for sample in samples:
        existing = input_pairs.get(sample.source_artifact_id)
        if existing is not None and existing != sample.source_content_hash:
            raise ValueError("PathForecast source Artifact hash conflict")
        input_pairs[sample.source_artifact_id] = sample.source_content_hash
    envelope = ArtifactEnvelope.create(
        artifact_type="PATH_FORECAST",
        artifact_payload=payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision=code_revision,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        source_manifest_id=signal_snapshot.envelope.source_manifest_id,
        source_manifest_hash=signal_snapshot.envelope.source_manifest_hash,
        input_artifact_ids=tuple(input_pairs),
        input_content_hashes=tuple(input_pairs.values()),
        model_id=configuration.model_id,
        model_version=configuration.model_version,
        data_eligibility=signal_snapshot.envelope.data_eligibility,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=status.value,
        reason_codes=reasons,
        limitations=(
            (
                "UNCALIBRATED_NO_PROBABILITY",
                "RESEARCH_FORECAST_NOT_ENTRY",
                "NO_TRADING_AUTHORITY",
            )
            if retrospective_event_ends is None
            else tuple(
                sorted(
                    {
                        "UNCALIBRATED_NO_PROBABILITY",
                        "RESEARCH_FORECAST_NOT_ENTRY",
                        "NO_TRADING_AUTHORITY",
                        "FORMAL_OOS_FALSE",
                        "PIT_INCOMPLETE",
                        "RETROSPECTIVE_EVENT_TIME",
                    }
                )
            )
        ),
    )
    return PathForecastArtifact(
        forecast=PathForecast(
            envelope=envelope,
            symbol=signal_snapshot.symbol,
            target_id=configuration.target_contract.target_id,
            forecast_horizon=configuration.horizon_label,
            upper_barrier_return=spec.upper_return,
            lower_barrier_return=spec.lower_return,
            expected_mfe=expected_mfe,
            expected_mae=expected_mae,
            return_quantiles=quantiles,
            calibration_status=calibration,
            forecast_status=status,
            usable_sample_count=len(usable),
            excluded_sample_count=len(excluded),
            reason_codes=reasons,
        ),
        signal_snapshot=signal_snapshot,
        configuration=configuration,
        samples=samples,
    )


def _linear_quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    if len(values) == 1:
        return values[0]
    location = (len(values) - 1) * probability
    lower_index = int(location)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = location - lower_index
    return values[lower_index] + fraction * (values[upper_index] - values[lower_index])


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("PathForecast numeric value is invalid")
    return float(value)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("PathForecast value must be an object")
    return value
